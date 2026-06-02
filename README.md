# Photos → NAS Transfer Wizard

Move your entire Google Photos library to a Synology NAS — with full EXIF metadata restoration, deduplication, and automatic folder organisation.

---

## What you get

- Extracts all Google Takeout `.zip` files directly (no manual unzipping)
- Restores correct **date taken** and **GPS location** into each JPEG/PNG from Google's JSON sidecar files
- **Video metadata embedding** — embeds creation dates and GPS into MP4, MOV, AVI, MKV videos (requires ffmpeg-python)
- **Advanced HEIC/TIFF support** — restores metadata into HEIC (iPhone) and TIFF archival formats (requires Pillow)
- Extracts and embeds **photo descriptions, keywords, orientation, and face recognition tags** from Google metadata
- Sets the file's **modified timestamp** on the NAS to match the original photo date
- **Deduplicates** photos (Google Takeout often exports the same photo twice when it appears in multiple albums)
- Organises photos into **Year / Month** folders on the NAS automatically
- Skips files already on the NAS so it's safe to re-run after an interruption
- Live progress log in the browser with separate tracking for photos vs videos

---

## Requirements

### On your computer

Python 3.8 or later is required on all platforms. Install the base dependencies once:

```
pip install paramiko piexif
```

**Optional dependencies** (for advanced metadata handling):

```
pip install ffmpeg-python pillow
```

- `ffmpeg-python` — required for embedding metadata into video files (MP4, MOV, AVI, MKV)
- `pillow` — required for HEIC and TIFF metadata embedding
- FFmpeg binary — download from [ffmpeg.org](https://ffmpeg.org/download.html) if you want video metadata support

#### Windows

- Download Python from [python.org](https://python.org) if not already installed — tick **"Add Python to PATH"** during setup
- Run the wizard from **PowerShell** or **Command Prompt**
- Paste zip folder paths using backslashes: `C:\Users\You\Downloads\Takeout`
- For video metadata: download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin` folder to your PATH

#### macOS

- Python 3 is available via [python.org](https://python.org) or Homebrew (`brew install python`)
- Run the wizard from **Terminal**
- Paste zip folder paths using forward slashes: `/Users/you/Downloads/Takeout`
- If `pip` is not found, try `pip3 install paramiko piexif`
- For video metadata: install FFmpeg via `brew install ffmpeg`

#### Linux

- Python 3 is pre-installed on most distributions. If not: `sudo apt install python3 python3-pip` (Debian/Ubuntu) or `sudo dnf install python3` (Fedora)
- Run the wizard from your **terminal**
- Paste zip folder paths using forward slashes: `/home/you/Downloads/Takeout`
- If pip is not found: `sudo apt install python3-pip`
- For video metadata: install FFmpeg via `sudo apt install ffmpeg` (Debian/Ubuntu)

### On your Synology NAS

- **SFTP enabled** — DSM → Control Panel → File Services → FTP tab → SFTP section → tick *Enable SFTP service* → Apply
- Your DSM user must have **Read/Write** permission on the destination shared folder — DSM → Control Panel → Shared Folder → select folder → Edit → Permission tab

---

## Files

| File | Purpose |
|------|---------|
| `sftp-run.py` | Python backend server — handles zip extraction, EXIF fixing, video metadata, and SFTP upload |
| `google-photos-to-nas.html` | Browser wizard UI — served automatically by the Python server |

Both files must be in the **same folder**.

---

## Quick start

### Step 1 — Request your Google Takeout

- Go to [takeout.google.com](https://takeout.google.com)
- Click **Deselect all**, then tick only **Google Photos**
- Click **Next step** → delivery: *Send download link via email* → format: `.zip` → size: **50 GB**
- Click **Create export** and wait for Google's email (can take hours or days for large libraries)
- Download all `.zip` files from the email into one folder on your computer — keep them zipped

> **Note:** Your Takeout will often be 1.5–2× larger than your Google storage shows, because photos that appear in multiple albums are exported multiple times. The wizard deduplicates them automatically.

### Step 2 — Run the wizard

Open a terminal (or PowerShell on Windows) in the folder containing the two files and run:

```
python sftp-run.py
```

On macOS/Linux, if `python` isn't found, try:

```
python3 sftp-run.py
```

Your browser will open automatically at `http://localhost:8000`. Keep the terminal window open during the transfer.

### Step 3 — Follow the wizard

The wizard walks you through 6 steps:

- **Guide** — pre-flight checklist (shown on first launch)
- **Zip folder** — paste the path to your Takeout download folder and click Scan
- **NAS setup** — enter your NAS IP, SSH port (default 22), username, password, and destination path
- **Options** — toggle metadata fixing, deduplication, skip-existing, and folder structure. Video metadata requires ffmpeg-python.
- **Transfer** — live log and progress bar while files upload. Separate counters for photos vs videos.
- **Done** — summary and next steps

---

## Finding the zip folder path

| Platform | How to get the path |
|----------|-------------------|
| **Windows** | Open the folder in File Explorer → click the address bar → copy the path (e.g. `C:\Users\Collins\Downloads\Takeout`) |
| **macOS** | Right-click the folder in Finder → hold Option → click *Copy "Takeout" as Pathname* (e.g. `/Users/collins/Downloads/Takeout`) |
| **Linux** | Right-click the folder in your file manager → Properties, or run `pwd` in the terminal after `cd`-ing into it |

---

## NAS destination path

The destination path must be the **real disk path** visible over SFTP, not the DSM display name.

| What you see in DSM | What to enter in the wizard |
|---------------------|-----------------------------|
| Shared folder `GooglePhotos` at `/volume1/GooglePhotos` | `Photos` *(if SFTP is chrooted to your home)* or `/volume1/GooglePhotos` |
| Shared folder `photo` at `/volume1/photo` | `/volume1/photo/GooglePhotos` |

**Tip:** Use the **Test SFTP connection** button on the NAS setup screen. It will connect, verify the path, and confirm write access before you start the full transfer. If the path is wrong, it will show diagnostic info.

If you see `SFTP cwd='/', root listing: ['Photos']` in the error, your session is chrooted to your home folder — use `Photos` as the destination path, or change the SFTP root in DSM → Control Panel → User → Edit → Home folder.

---

## Metadata restoration

Google Takeout strips the original date and GPS location from photo files and stores them separately in `.json` sidecar files. The wizard restores all this metadata automatically.

### What gets restored per file type

| Format | Date Taken | GPS coordinates | Description | Keywords | Orientation | Face Tags |
|--------|-----------|-----------------|-------------|----------|-------------|-----------|
| JPEG / JPG | ✅ EXIF embedded | ✅ EXIF embedded | ✅ EXIF | ✅ EXIF | ✅ EXIF | ✅ User comment |
| PNG | ✅ tEXt chunk | — | ✅ tEXt | ✅ tEXt | ✅ tEXt | ✅ tEXt |
| HEIC / iPhone | ✅ EXIF | ✅ EXIF | ✅ EXIF | ✅ Keywords | ✅ Orientation | ⚠ Limited |
| TIFF / Archive | ✅ EXIF | ✅ EXIF | ✅ EXIF | ✅ Keywords | ✅ EXIF | ⚠ Limited |
| MP4 / MOV | ✅ creation_time | ⚠ format-limited | — | — | — | — |
| AVI / MKV | ✅ creation_time | ⚠ format-limited | — | — | — | — |
| Video (other) | — needs manual | — | — | — | — | — |

### Technical notes

The wizard handles all Google's sidecar naming formats:

| Photo file | Sidecar Google creates |
|------------|------------------------|
| `photo.jpg` | `photo.jpg.json` or `photo.json` |
| `photo(1).jpg` | `photo(1).jpg.json` |
| Long filenames | Truncated to 46 characters |
| Some exports | `photo.jpg.supplemental-metadata.json` |

**Video metadata embedding** uses FFmpeg's lossless metadata injection (`-c copy` codec flags), so no re-encoding happens — videos transfer at full speed.

**HEIC/TIFF support** requires Pillow (PIL). If not installed, these formats will be skipped with a warning in the log.

---

## Troubleshooting

**"Access Denied" on upload**
- Check DSM → Control Panel → Shared Folder → Edit → Permission tab — your user needs Read/Write
- Make sure the path uses `/volume1/...` not `/photo/...` — unless you're chrooted (see NAS destination path section above)

**"Authentication failed"**
- Double-check your DSM username and password
- Make sure SFTP is enabled (not just SSH) in DSM → File Services → FTP → SFTP

**"Folder not found" on scan**
- Windows: use backslashes — `C:\Users\You\Downloads\Takeout`
- macOS/Linux: use forward slashes — `/Users/you/Downloads/Takeout`
- Copy the path directly from your file manager to avoid typos

**`python` command not found (macOS/Linux)**
- Try `python3 sftp-run.py` instead
- On macOS you may need to install Python via [python.org](https://python.org) or `brew install python`

**`pip` command not found**
- Try `pip3 install paramiko piexif` (and `ffmpeg-python pillow` for optional features)
- On Linux: `sudo apt install python3-pip` then retry

**Browser doesn't open automatically**
- Manually open `http://localhost:8000` in your browser

**Transfer interrupted**
- Just run the wizard again with the same settings — with *Skip already-uploaded files* enabled it will resume from where it left off without re-uploading anything

**EXIF not restored on some files**
- The wizard logs `No sidecar found for: filename.jpg` when Google didn't include a JSON for that file
- This can happen with photos synced from other apps — the original date may already be embedded in the file
- For videos without metadata, the wizard logs a warning; consider using external tools like ExifTool if manual tagging is needed

**ffmpeg not found (video metadata)**
- Install FFmpeg: Windows ([ffmpeg.org](https://ffmpeg.org/download.html)), macOS (`brew install ffmpeg`), Linux (`sudo apt install ffmpeg`)
- Verify it's in your PATH by running `ffmpeg -version` in terminal
- Without ffmpeg, the wizard will log warnings and skip video metadata

**Pillow import error (HEIC/TIFF)**
- Install Pillow: `pip install pillow` (or `pip3` on macOS/Linux)
- Without Pillow, HEIC and TIFF files will be transferred but metadata won't be embedded — log will show warnings

---

## After the transfer

- Open **Synology Photos** on your NAS — your library will be indexed automatically
- Install the **Synology Photos** app on your phone (Android / iOS) and enable auto-backup so new photos go straight to the NAS going forward
- Once you've verified everything looks correct on the NAS, delete the Takeout zip files from your computer to free up space
- Consider cancelling your Google One subscription if you were paying for extra storage

---

## Dependencies

| Package | Purpose | Required? |
|---------|---------|-----------|
| `paramiko` | SFTP connection to Synology NAS | **Yes** |
| `piexif` | Read and write EXIF metadata in JPEG files | **Yes** |
| `ffmpeg-python` | Embed metadata into video files | Optional — videos will be skipped if missing |
| `pillow` (PIL) | HEIC and TIFF metadata embedding | Optional — these formats will be skipped if missing |
| FFmpeg binary | Required by ffmpeg-python for video processing | Optional — only if you want video metadata |

Install core dependencies with: `pip install paramiko piexif`

Install all optional dependencies with: `pip install ffmpeg-python pillow`

(On macOS/Linux, use `pip3` if `pip` isn't in your PATH)
