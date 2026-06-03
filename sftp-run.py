import http.server
import socketserver
import json
import os
import io
import re
import threading
import zipfile
import hashlib
import webbrowser
import struct
import paramiko
from datetime import datetime, timezone
from pathlib import Path

PORT = 8000
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'google-photos-to-nas.html')

PHOTO_EXTS  = {'.jpg','.jpeg','.png','.gif','.bmp','.webp','.heic','.heif','.tiff','.tif'}
VIDEO_EXTS  = {'.mp4','.mov','.avi','.mkv','.3gp','.m4v','.wmv','.mts'}
ALL_EXTS    = PHOTO_EXTS | VIDEO_EXTS

# Try importing optional dependencies
try:
    import ffmpeg
    HAS_FFMPEG = True
except ImportError:
    HAS_FFMPEG = False

try:
    from PIL import Image
    import piexif as pil_exif
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

transfer_status = {
    "running": False, "done": False,
    "uploaded": 0, "skipped": 0, "errors": 0, "total": 0,
    "photos_processed": 0, "videos_processed": 0,
    "meta_fixed": 0,
    "phase": "", "pct": 0, "current_file": "",
    "log": [], "error": None
}
status_lock = threading.Lock()

# ── Logging ───────────────────────────────────────────────────────────
def bg_log(msg, level="info"):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "text": msg, "level": level}
    print(f"[{entry['time']}] {msg}")
    with status_lock:
        transfer_status["log"].append(entry)

def set_phase(phase, pct=None):
    with status_lock:
        transfer_status["phase"] = phase
        if pct is not None:
            transfer_status["pct"] = pct

# ── Metadata helpers ────────────────────────────────────────────────────────

def extract_media_filename_from_json(json_basename):
    """
    Extract the media filename from a JSON sidecar filename.
    Handles both full and truncated names.
    
    Examples:
    - "image.jpg.json" → "image.jpg"
    - "image.jpg.supplemental-metadata.json" → "image.jpg"
    - "image.jpg.supplemental-met.json" (truncated) → "image.jpg"
    - "image(1).jpg.json" → "image(1).jpg"
    
    Returns the media filename, or None if it can't be determined.
    """
    if not json_basename.endswith(".json"):
        return None
    
    # Remove .json extension
    without_json = json_basename[:-5]
    
    # Try to find where the media extension is
    # Look for known media extensions in the filename
    media_ext_pattern = r'\.(jpg|jpeg|png|gif|bmp|webp|heic|heif|tiff|tif|mp4|mov|avi|mkv|3gp|m4v|wmv|mts)(?:\.|$)'
    match = re.search(media_ext_pattern, without_json, re.IGNORECASE)
    
    if not match:
        return None
    
    # Get everything up to and including the media extension
    end_pos = match.end(1) + 1  # +1 to include the dot before extension
    media_filename = without_json[:end_pos]
    
    return media_filename


def find_matching_json(json_basename, all_media_files):
    """
    Find which media file this JSON sidecar belongs to.
    Handles exact matches and fuzzy matching for truncated filenames.
    
    Returns the media filename that this JSON describes, or None.
    """
    media_filename = extract_media_filename_from_json(json_basename)
    
    if not media_filename:
        return None
    
    # Try exact match first
    if media_filename in all_media_files:
        return media_filename
    
    # If no exact match, try fuzzy matching for truncated names
    # The media_filename extraction should work for most cases,
    # but in case of edge cases, try prefix matching
    for media_file in all_media_files:
        if media_file.startswith(media_filename[:min(len(media_filename), 30)]):
            # Additional validation: media file should also start with media_filename
            if media_file.lower().startswith(media_filename.lower()):
                return media_file
    
    return None


def find_meta_for(fname, meta_map):
    """
    Direct lookup: try to find metadata for a file by matching its basename
    in the meta_map. Meta_map keys are media basenames.
    """
    if fname in meta_map:
        return meta_map[fname]
    return None


def parse_timestamp(meta):
    """Return (datetime_utc, year, month) from Google meta dict, or (None, None, None)."""
    for key in ("photoTakenTime", "creationTime"):
        v = meta.get(key, {})
        ts = v.get("timestamp")
        if ts:
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                return dt, dt.year, dt.month
            except Exception:
                pass
    return None, None, None


def parse_gps(meta):
    """Return (lat, lon, alt) floats or (None, None, None)."""
    geo = meta.get("geoData") or meta.get("geoDataExif")
    if not geo:
        return None, None, None
    lat = geo.get("latitude")
    lon = geo.get("longitude")
    alt = geo.get("altitude")
    if lat is not None and lon is not None and (lat != 0.0 or lon != 0.0):
        return float(lat), float(lon), float(alt) if alt else 0.0
    return None, None, None


def parse_description(meta):
    """Return description/caption from Google metadata, or None."""
    return meta.get("description") or meta.get("caption")


def parse_keywords(meta):
    """Return keywords/album tags from Google metadata as list, or empty list."""
    keywords = []
    # Try to get album info
    albums = meta.get("albumLabels", [])
    if albums and isinstance(albums, list):
        keywords.extend(albums)
    # Try explicit keywords field
    if meta.get("keywords"):
        kw = meta.get("keywords")
        if isinstance(kw, list):
            keywords.extend(kw)
        else:
            keywords.append(str(kw))
    return keywords


def parse_orientation(meta):
    """Return EXIF orientation (1-8) from Google metadata, or None."""
    # Google may store orientation in different places
    if meta.get("orientation"):
        try:
            return int(meta.get("orientation"))
        except (ValueError, TypeError):
            pass
    return None


def parse_people_tags(meta):
    """Return face recognition/people tags from Google metadata as string, or None."""
    people = meta.get("peopleNames") or meta.get("faceRegions")
    if people:
        if isinstance(people, list):
            return ", ".join(str(p) for p in people)
        else:
            return str(people)
    return None


def dms_rational(deg):
    """Convert decimal degrees to EXIF rational (degrees, minutes, seconds)."""
    d = int(abs(deg))
    m_float = (abs(deg) - d) * 60
    m = int(m_float)
    s_float = (m_float - m) * 60
    # Store as (numerator, denominator) tuples
    return [(d, 1), (m, 1), (int(s_float * 1000), 1000)]


def embed_exif_jpeg(data: bytes, dt: datetime, lat, lon, alt, desc=None, keywords=None, orientation=None, people=None) -> bytes:
    """
    Embed DateTimeOriginal + GPS + description + keywords + orientation + people into a JPEG using piexif.
    Falls back to returning original data if anything fails.
    """
    try:
        import piexif
        import tempfile

        try:
            exif_dict = piexif.load(io.BytesIO(data))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        if dt:
            dt_str = dt.strftime("%Y:%m:%d %H:%M:%S").encode()
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal]  = dt_str
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str
            exif_dict["0th"][piexif.ImageIFD.DateTime]          = dt_str

        if lat is not None and lon is not None:
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef]  = b"N" if lat >= 0 else b"S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude]     = dms_rational(lat)
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude]    = dms_rational(lon)
            if alt is not None:
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = b"\x00"
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitude]    = (int(abs(alt) * 100), 100)

        if orientation and 1 <= orientation <= 8:
            exif_dict["0th"][piexif.ImageIFD.Orientation] = orientation

        if desc:
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = desc[:1000].encode()

        if people:
            # Store in EXIF user comment with proper charset prefix (ASCII)
            # Format: b'\x00' (ASCII charset) + comment bytes
            people_bytes = people[:1000].encode('utf-8', errors='ignore')
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = b'\x00' + people_bytes

        exif_bytes = piexif.dump(exif_dict)
        
        # piexif.insert() requires a file path. Use a temp file, read result, then delete.
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(data)
        
        try:
            piexif.insert(exif_bytes, tmp_path)
            with open(tmp_path, 'rb') as f:
                result = f.read()
            return result
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
                
    except Exception as e:
        bg_log(f"EXIF embed warning: {e}", "warn")
        return data


def embed_exif_png(data: bytes, dt: datetime, desc=None, keywords=None, orientation=None, people=None) -> bytes:
    """
    Embed creation time into PNG as a tEXt chunk, plus description, keywords, orientation.
    PNG doesn't support EXIF dates natively the same way; tEXt is widely read.
    """
    try:
        if not dt:
            return data
        
        chunks = []
        key = b"Creation Time"
        val = dt.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
        chunk_data = key + b"\x00" + val
        crc = _png_crc(b"tEXt" + chunk_data)
        chunks.append(struct.pack(">I", len(chunk_data)) + b"tEXt" + chunk_data + struct.pack(">I", crc))

        if desc:
            key = b"Description"
            val = desc[:1000].encode()
            chunk_data = key + b"\x00" + val
            crc = _png_crc(b"tEXt" + chunk_data)
            chunks.append(struct.pack(">I", len(chunk_data)) + b"tEXt" + chunk_data + struct.pack(">I", crc))

        if keywords:
            key = b"Keywords"
            kw_str = ", ".join(keywords) if isinstance(keywords, list) else keywords
            val = kw_str[:1000].encode()
            chunk_data = key + b"\x00" + val
            crc = _png_crc(b"tEXt" + chunk_data)
            chunks.append(struct.pack(">I", len(chunk_data)) + b"tEXt" + chunk_data + struct.pack(">I", crc))

        if orientation:
            key = b"Orientation"
            val = str(orientation).encode()
            chunk_data = key + b"\x00" + val
            crc = _png_crc(b"tEXt" + chunk_data)
            chunks.append(struct.pack(">I", len(chunk_data)) + b"tEXt" + chunk_data + struct.pack(">I", crc))

        if people:
            key = b"People"
            val = people[:1000].encode()
            chunk_data = key + b"\x00" + val
            crc = _png_crc(b"tEXt" + chunk_data)
            chunks.append(struct.pack(">I", len(chunk_data)) + b"tEXt" + chunk_data + struct.pack(">I", crc))

        # Insert before IEND (last 12 bytes)
        result = data[:-12]
        for chunk in chunks:
            result += chunk
        result += data[-12:]
        return result
    except Exception:
        return data


def _png_crc(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


def embed_exif_tiff(data: bytes, dt: datetime, lat, lon, alt, desc=None, keywords=None, orientation=None, people=None) -> bytes:
    """
    Embed metadata into TIFF files by re-encoding with Pillow.
    Uses piexif for EXIF data manipulation if available.
    """
    if not HAS_PILLOW:
        bg_log(f"Pillow not installed — TIFF metadata embedding skipped", "warn")
        return data
    
    try:
        img = Image.open(io.BytesIO(data))
        
        # Build EXIF dict using piexif if available
        try:
            import piexif
            exif_dict = piexif.load(io.BytesIO(data))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        if dt:
            dt_str = dt.strftime("%Y:%m:%d %H:%M:%S").encode()
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal]  = dt_str
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt_str
            exif_dict["0th"][piexif.ImageIFD.DateTime]          = dt_str

        if lat is not None and lon is not None:
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef]  = b"N" if lat >= 0 else b"S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude]     = dms_rational(lat)
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude]    = dms_rational(lon)
            if alt is not None:
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = b"\x00"
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitude]    = (int(abs(alt) * 100), 100)

        if orientation and 1 <= orientation <= 8:
            exif_dict["0th"][piexif.ImageIFD.Orientation] = orientation

        if desc:
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = desc[:1000].encode()

        # For TIFF, save with EXIF data
        exif_bytes = piexif.dump(exif_dict)
        output = io.BytesIO()
        img.save(output, format='TIFF', exif=exif_bytes)
        return output.getvalue()
    except Exception as e:
        bg_log(f"TIFF metadata embedding warning: {e}", "warn")
        return data


def embed_metadata_video(fname: str, data: bytes, meta: dict) -> tuple:
    """
    Embed metadata into video files using ffmpeg.
    Returns (modified_data, was_modified).
    Losslessly copies streams while embedding metadata.
    """
    if not HAS_FFMPEG:
        bg_log(f"  ↳ {fname}: ffmpeg-python not installed — video metadata skipped", "warn")
        return data, False

    try:
        dt, _, _ = parse_timestamp(meta)
        lat, lon, alt = parse_gps(meta)

        if not (dt or lat):
            return data, False  # No metadata to add

        # Create temp files for ffmpeg processing
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(fname)[1], delete=False) as tmp_in:
            tmp_in_path = tmp_in.name
            tmp_in.write(data)

        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(fname)[1], delete=False) as tmp_out:
            tmp_out_path = tmp_out.name

        try:
            # Build ffmpeg command with metadata - use list of arguments to avoid key collision
            stream = ffmpeg.input(tmp_in_path)
            output_kwargs = {'c:v': 'copy', 'c:a': 'copy'}  # Lossless copy
            
            if dt:
                creation_time = dt.strftime("%Y-%m-%dT%H:%M:%S")
                output_kwargs['metadata:g'] = f"creation_time={creation_time}"
            
            # Note: GPS metadata cannot coexist with creation_time in the same metadata:g key
            # So we only embed GPS if there's no creation time, or as separate metadata
            if lat is not None and lon is not None:
                # For video, GPS format is container-specific. Skip if we already set creation_time.
                if 'metadata:g' not in output_kwargs:
                    gps_str = f"lat={lat:.6f},lon={lon:.6f}"
                    if alt is not None:
                        gps_str += f",alt={alt:.2f}"
                    output_kwargs['metadata:g'] = gps_str
            
            stream = ffmpeg.output(stream, tmp_out_path, **output_kwargs)
            ffmpeg.run(stream, overwrite_output=True, quiet=True)

            # Read modified video
            with open(tmp_out_path, 'rb') as f:
                new_data = f.read()

            return new_data, True

        except Exception as e:
            bg_log(f"  ↳ {fname}: video metadata embedding failed: {e}", "warn")
            return data, False
        finally:
            # Clean up temp files
            try:
                os.remove(tmp_in_path)
                os.remove(tmp_out_path)
            except Exception:
                pass

    except Exception as e:
        bg_log(f"  ↳ {fname}: video processing error: {e}", "warn")
        return data, False


def apply_metadata(fname: str, data: bytes, meta: dict) -> tuple:
    """
    Apply date + GPS + description + keywords + orientation + people metadata to the file bytes.
    Returns (modified_data, was_modified).
    """
    ext = os.path.splitext(fname)[1].lower()
    if ext not in PHOTO_EXTS and ext not in VIDEO_EXTS:
        return data, False

    dt, _, _ = parse_timestamp(meta)
    lat, lon, alt = parse_gps(meta)
    desc = parse_description(meta)
    keywords = parse_keywords(meta)
    orientation = parse_orientation(meta)
    people = parse_people_tags(meta)

    # Videos use special handling
    if ext in VIDEO_EXTS:
        return embed_metadata_video(fname, data, meta)

    # Photos with enhanced metadata
    if ext in ('.jpg', '.jpeg'):
        new_data = embed_exif_jpeg(data, dt, lat, lon, alt, desc, keywords, orientation, people)
        return new_data, new_data != data

    if ext == '.png':
        new_data = embed_exif_png(data, dt, desc, keywords, orientation, people)
        return new_data, new_data != data

    if ext in ('.heic', '.heif'):
        # HEIC: save without re-encoding to avoid corruption
        if not HAS_PILLOW:
            bg_log(f"  ↳ {fname}: Pillow not installed — HEIC transferred without metadata", "warn")
            return data, False
        # For HEIC, just transfer as-is since Pillow can't reliably write HEIC with metadata
        # Log that we found metadata but can't embed it
        if dt or lat or desc:
            bg_log(f"  ↳ {fname}: HEIC metadata found but embedding requires external tools like exiftool", "warn")
        return data, False

    if ext in ('.tiff', '.tif'):
        new_data = embed_exif_tiff(data, dt, lat, lon, alt, desc, keywords, orientation, people)
        return new_data, new_data != data

    # Other formats — at least log that metadata was found
    if dt or lat or desc:
        bg_log(f"  ↳ {fname}: metadata found but format {ext} not yet supported", "warn")
    return data, False


# ── SFTP helpers ─────────────────────────────────────────────────────────

def sftp_makedirs(sftp, remote_path):
    """Create remote directories, handling absolute and relative paths correctly."""
    parts = [p for p in remote_path.replace("\\", "/").split("/") if p]
    
    if not parts:
        return  # Empty path
    
    is_absolute = remote_path.startswith("/")
    
    for i, part in enumerate(parts):
        if is_absolute:
            # Absolute path: /a/b/c → build /, /a, /a/b, /a/b/c
            path = "/" + "/".join(parts[:i+1])
        else:
            # Relative path: a/b/c → build a, a/b, a/b/c
            path = "/".join(parts[:i+1])
        
        try:
            sftp.stat(path)
        except FileNotFoundError:
            try:
                sftp.mkdir(path)
            except Exception:
                pass


def detect_sftp_base(sftp, nas_base):
    """
    Synology chroots SFTP sessions. Detect the real working path.
    Returns the path string that actually works over SFTP.
    """
    candidates = [nas_base]
    stripped = re.sub(r"^/volume\d+", "", nas_base)
    if stripped and stripped != nas_base:
        candidates.append(stripped)
    rel = stripped.lstrip("/")
    if rel:
        candidates.append(rel)

    for p in candidates:
        try:
            sftp.listdir(p)
            return p
        except Exception:
            continue

    # Path doesn't exist yet — try parent to verify we can reach that level
    for p in candidates:
        parent = "/".join(p.rstrip("/").split("/")[:-1]) or "/"
        try:
            sftp.listdir(parent)
            return p  # parent exists, will create leaf later
        except Exception:
            continue

    return candidates[-1]  # best guess


def sha1_blob(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def subfolder(year, month, mode):
    if mode == "year-month" and year:
        return f"{year}/{str(month).zfill(2)}"
    elif mode == "year" and year:
        return str(year)
    return ""


# ── Main transfer job ────────────────────────────────────────────────────────

def run_transfer(config):
    with status_lock:
        transfer_status.update({
            "running": True, "done": False, "uploaded": 0, "skipped": 0,
            "errors": 0, "total": 0, "photos_processed": 0, "videos_processed": 0,
            "meta_fixed": 0,
            "phase": "", "pct": 0, "current_file": "", "log": [], "error": None
        })

    zip_paths = config.get("files", [])
    nas_host  = config["nasHost"]
    nas_port  = int(config.get("nasPort", 22))
    nas_user  = config["nasUser"]
    nas_pass  = config["nasPass"]
    nas_base  = config["nasPath"].rstrip("/")
    do_dedup  = config.get("dedup", True)
    skip_ex   = config.get("skipExisting", True)
    fold_mode = config.get("folderMode", "year-month")
    do_meta   = config.get("meta", True)

    seen_hashes = set()

    try:
        # ── Phase 1: Scan zips & build metadata map ───────────────────────────
        set_phase("Scanning zip files", 2)
        bg_log(f"Scanning {len(zip_paths)} zip file(s)…", "info")

        all_entries = []   # list of (zip_path, ZipInfo)
        meta_map    = {}   # key: media basename, value: merged metadata dict
        all_media_files = set()  # Track all media filenames for fuzzy matching

        for zp in zip_paths:
            zname = os.path.basename(zp)
            bg_log(f"Opening {zname}…")
            try:
                with zipfile.ZipFile(zp, 'r') as z:
                    # First pass: collect all media filenames
                    for info in z.infolist():
                        name = info.filename
                        ext  = os.path.splitext(name)[1].lower()
                        if ext in ALL_EXTS:
                            media_basename = os.path.basename(name)
                            all_media_files.add(media_basename)
                    
                    # Second pass: process all files
                    for info in z.infolist():
                        name = info.filename
                        ext  = os.path.splitext(name)[1].lower()

                        if ext in ALL_EXTS:
                            # Media file: store it
                            all_entries.append((zp, info))

                        elif ext == ".json":
                            # ANY .json file could be metadata
                            try:
                                raw  = z.read(name)
                                meta = json.loads(raw.decode("utf-8", errors="ignore"))
                                
                                if isinstance(meta, dict) and len(meta) > 0:
                                    json_basename = os.path.basename(name)
                                    
                                    # Use fuzzy matching to find the media file this JSON belongs to
                                    matched_media = find_matching_json(json_basename, all_media_files)
                                    
                                    if matched_media:
                                        # Merge metadata: if we have multiple JSON files for same media, merge them
                                        if matched_media not in meta_map:
                                            meta_map[matched_media] = meta
                                        else:
                                            meta_map[matched_media].update(meta)
                            except Exception:
                                pass
            except Exception as e:
                bg_log(f"Cannot open {zname}: {e}", "err")

        total = len(all_entries)
        with status_lock:
            transfer_status["total"] = total
        bg_log(f"Found {total} photo/video files.", "ok")
        bg_log(f"Loaded {len(meta_map)} metadata entries.", "ok")
        set_phase("Scan complete", 15)

        # ── Phase 2: Connect SFTP ─────────────────────────────────────────────
        set_phase("Connecting to NAS", 18)
        bg_log(f"Connecting to {nas_host}:{nas_port} via SFTP…", "info")

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(nas_host, port=nas_port, username=nas_user,
                    password=nas_pass, timeout=15,
                    allow_agent=False, look_for_keys=False)
        sftp = ssh.open_sftp()
        bg_log("SFTP connected.", "ok")

        sftp_base = detect_sftp_base(sftp, nas_base)
        if sftp_base != nas_base:
            bg_log(f"Chroot detected — using SFTP path: '{sftp_base}'", "warn")
        else:
            bg_log(f"Destination path: {sftp_base}", "ok")

        sftp_makedirs(sftp, sftp_base)

        # ── Phase 3: Upload ───────────────────────────────────────────────────
        set_phase("Uploading", 22)
        bg_log(f"Starting upload of {total} files…", "info")

        created_dirs = set()

        for i, (zp, info) in enumerate(all_entries):
            fname = os.path.basename(info.filename)
            ext = os.path.splitext(fname)[1].lower()
            is_video = ext in VIDEO_EXTS
            
            with status_lock:
                transfer_status["current_file"] = fname
                transfer_status["pct"] = 22 + int(i / max(total, 1) * 75)

            try:
                with zipfile.ZipFile(zp, 'r') as z:
                    data = z.read(info.filename)

                # ── Dedup ─────────────────────────────────────────────────────
                if do_dedup:
                    h = sha1_blob(data)
                    if h in seen_hashes:
                        with status_lock: transfer_status["skipped"] += 1
                        bg_log(f"Duplicate skipped: {fname}", "warn")
                        continue
                    seen_hashes.add(h)

                # ── Find metadata & apply EXIF ────────────────────────────────
                meta = find_meta_for(fname, meta_map) if do_meta else None
                dt, year, month = parse_timestamp(meta) if meta else (None, None, None)

                if meta and do_meta:
                    data, was_fixed = apply_metadata(fname, data, meta)
                    if was_fixed:
                        with status_lock: 
                            transfer_status["meta_fixed"] += 1
                            if is_video:
                                transfer_status["videos_processed"] += 1
                            else:
                                transfer_status["photos_processed"] += 1
                        
                        lat, lon, _ = parse_gps(meta)
                        gps_note = f" GPS({lat:.4f},{lon:.4f})" if lat else ""
                        file_type = "Video" if is_video else "Photo"
                        bg_log(f"  ↳ {file_type} metadata restored: {dt.strftime('%Y-%m-%d %H:%M') if dt else '?'}{gps_note} → {fname}", "ok")
                elif meta is None and do_meta:
                    bg_log(f"  ↳ No sidecar found for: {fname}", "warn")

                # ── Destination path ──────────────────────────────────────────
                sub      = subfolder(year, month, fold_mode)
                dest_dir = f"{sftp_base}/{sub}".rstrip("/") if sub else sftp_base
                dest_path = f"{dest_dir}/{fname}"

                if dest_dir not in created_dirs:
                    sftp_makedirs(sftp, dest_dir)
                    created_dirs.add(dest_dir)

                # ── Skip existing ─────────────────────────────────────────────
                if skip_ex:
                    try:
                        sftp.stat(dest_path)
                        with status_lock: transfer_status["skipped"] += 1
                        bg_log(f"Already on NAS, skipped: {fname}", "warn")
                        continue
                    except FileNotFoundError:
                        pass

                # ── Upload ────────────────────────────────────────────────────
                sftp.putfo(io.BytesIO(data), dest_path)

                # Set file modification time to match photo date
                if dt:
                    ts = int(dt.timestamp())
                    try:
                        sftp.utime(dest_path, (ts, ts))
                    except Exception:
                        pass

                with status_lock: transfer_status["uploaded"] += 1
                bg_log(f"✓ {dest_path}", "ok")

            except Exception as e:
                with status_lock: transfer_status["errors"] += 1
                err_str = str(e)
                if "Permission denied" in err_str or "Access denied" in err_str:
                    bg_log(f"ACCESS DENIED: {fname} — check DSM folder permissions.", "err")
                else:
                    bg_log(f"Error on {fname}: {err_str}", "err")

        sftp.close()
        ssh.close()

        with status_lock:
            mf = transfer_status["meta_fixed"]
            vp = transfer_status["videos_processed"]
            pp = transfer_status["photos_processed"]
        
        if vp > 0 or pp > 0:
            bg_log(f"Transfer complete. Metadata restored on {mf} file(s): {pp} photo(s), {vp} video(s).", "ok")
        else:
            bg_log(f"Transfer complete. EXIF metadata restored on {mf} file(s).", "ok")
        set_phase("Complete", 100)

    except paramiko.AuthenticationException:
        bg_log("Authentication failed — wrong username or password.", "err")
        with status_lock: transfer_status["error"] = "Authentication failed"
    except Exception as e:
        import traceback
        bg_log(f"Fatal error: {e}", "err")
        print(traceback.format_exc())
        with status_lock: transfer_status["error"] = str(e)

    with status_lock:
        transfer_status["running"] = False
        transfer_status["done"]    = True


# ── HTTP handler ─────────────────────────────────────────────────────────

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            with open(HTML_FILE, "rb") as f:
                self.wfile.write(f.read())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            with status_lock:
                self.wfile.write(json.dumps(transfer_status).encode())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/api/scan-folder":
            folder = body.get("folder", "").strip()
            if not os.path.isdir(folder):
                self._json({"ok": False, "error": f"Folder not found: {folder}"}); return
            files = []
            total_bytes = 0
            for fname in sorted(os.listdir(folder)):
                if fname.lower().endswith(".zip"):
                    fp = os.path.join(folder, fname)
                    sz = os.path.getsize(fp)
                    files.append({"name": fname, "path": fp, "size": sz})
                    total_bytes += sz
            self._json({"ok": True, "files": files, "total_bytes": total_bytes})

        elif self.path == "/api/start":
            if transfer_status["running"]:
                self._json({"ok": False, "error": "Already running"}); return
            folder = body.get("folder", "").strip()
            zip_paths = []
            if os.path.isdir(folder):
                for fname in sorted(os.listdir(folder)):
                    if fname.lower().endswith(".zip"):
                        zip_paths.append(os.path.join(folder, fname))
            body["files"] = zip_paths
            threading.Thread(target=run_transfer, args=(body,), daemon=True).start()
            self._json({"ok": True})

        elif self.path == "/api/reset":
            with status_lock:
                transfer_status.update({
                    "running": False, "done": False, "uploaded": 0, "skipped": 0,
                    "errors": 0, "total": 0, "photos_processed": 0, "videos_processed": 0,
                    "meta_fixed": 0,
                    "phase": "", "pct": 0, "current_file": "", "log": [], "error": None
                })
            self._json({"ok": True})

        elif self.path == "/api/test-sftp":
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(body["host"], port=int(body.get("port", 22)),
                            username=body["user"], password=body["pass"],
                            timeout=10, allow_agent=False, look_for_keys=False)
                sftp = ssh.open_sftp()
                target = body.get("path", "").rstrip("/")

                try:
                    cwd = sftp.getcwd() or "/"
                except Exception:
                    cwd = "unknown"
                try:
                    root_listing = sftp.listdir("/")
                except Exception as e:
                    root_listing = [f"(error: {e})"]

                diag = f"SFTP cwd='{cwd}', root: {root_listing[:12]}"

                candidates = [target]
                stripped = re.sub(r"^/volume\d+", "", target)
                if stripped and stripped != target:
                    candidates.append(stripped)
                rel = stripped.lstrip("/")
                if rel:
                    candidates.append(rel)

                path_ok  = False
                path_msg = ""
                for p in candidates:
                    try:
                        sftp.listdir(p)
                        test_file = p.rstrip("/") + "/.write_test_tmp"
                        try:
                            sftp.putfo(io.BytesIO(b"ok"), test_file)
                            sftp.remove(test_file)
                            path_ok  = True
                            path_msg = f"✓ Path '{p}' accessible with write permission. Ready to transfer!"
                        except Exception as we:
                            path_msg = (f"Path '{p}' found but write failed: {we}. "
                                        f"Check DSM → Shared Folder → Edit → Permission tab.")
                        break
                    except Exception:
                        continue

                if not path_msg:
                    path_ok  = False
                    path_msg = (f"Could not access any of: {candidates}. "
                                f"Diagnostic — {diag}. Copy this and share it.")

                sftp.close(); ssh.close()
                self._json({"ok": True, "path_ok": path_ok, "path_msg": path_msg, "diag": diag})

            except paramiko.AuthenticationException:
                self._json({"ok": False, "error": "Wrong username or password"})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})

        else:
            self.send_response(404); self.end_headers()

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


# ── Entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    print("\n  ┌──────────────────────────────────────────┐")
    print("  │   Photos → NAS  (SFTP + EXIF edition)   │")
    print("  ├──────────────────────────────────────────┤")
    print(f"  │   Open:  http://localhost:{PORT}             │")
    print("  │   Stop:  Ctrl+C                          │")
    print("  └──────────────────────────────────────────┘\n")
    
    # Log optional dependency availability
    if not HAS_FFMPEG:
        print("  ⚠ ffmpeg-python not installed — video metadata embedding disabled")
        print("    Install with: pip install ffmpeg-python")
    if not HAS_PILLOW:
        print("  ⚠ Pillow not installed — TIFF metadata embedding disabled")
        print("    Install with: pip install pillow")
    
    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()
