# Photos → NAS Transfer Wizard

Move your entire Google Photos library to a Synology NAS — with full EXIF metadata restoration, deduplication, and automatic folder organisation.

---

## What you get

- Extracts all Google Takeout `.zip` files directly (no manual unzipping)
- Restores correct **date taken** and **GPS location** into each JPEG/PNG from Google's JSON sidecar files
- Restores **descriptions/captions**, **album keywords**, **orientation**, and **people/face tags** where available
- Sets the file's **modified timestamp** on the NAS to match the original photo date
- Embeds metadata into **videos** (creation time + GPS) using ffmpeg — optional, see Dependencies
- **Deduplicates** photos (Google Takeout often exports the same photo twice when it appears in multiple albums)
- Organises photos into **Year / Month** folders on the NAS automatically
- Skips files already on the NAS so it's safe to re-run after an interruption
- Uploads with **4 parallel SFTP channels** for faster transfers
- Live progress log in the browser

---

## Requirements

### On your computer

Python 3.8 or later is required on all platforms. Install the required dependencies once:

```
pip install paramiko piexif
```

**Optional — for extended format support:**

```
pip install ffmpeg-python   # video metadata embedding (creation time + GPS)
pip install pillow          # TIFF metadata embedding
```

The wizard works without these — photos and videos still transfer, but video metadata and TIFF metadata embedding are skipped with a warning.

#### Windows

- Download Python from [python.org](https://python.org) if not already installed — tick **"Add Python to PATH"** during setup
- Run the wizard from **PowerShell** or **Command Prompt**
- Paste zip folder paths using backslashes: `C:\Users\You\Downloads\Takeout`

#### macOS

- Python 3 is available via [python.org](https://python.org) or Homebrew (`brew install python`)
- Run the wizard from **Terminal**
- Paste zip folder paths using forward slashes: `/Users/you/Downloads/Takeout`
- If `pip` is not found, try `pip3 install paramiko piexif`

#### Linux

- Python 3 is pre-installed on most distributions. If not: `sudo apt install python3 python3-pip` (Debian/Ubuntu) or `sudo dnf install python3` (Fedora)
- Run the wizard from your **terminal**
- Paste zip folder paths using forward slashes: `/home/you/Downloads/Takeout`
- If pip is not found: `sudo apt install python3-pip`

### On your Synology NAS

- **SSH enabled** — DSM → Control Panel → Terminal & SNMP → tick *Enable SSH service* → Apply (SFTP runs over SSH)
- Your DSM user must have **Read/Write** permission on the destination shared folder — DSM → Control Panel → Shared Folder → select folder → Edit → Permission tab

---

## Files

| File | Purpose |
|------|---------|
| `sftp-run.py` | Python backend server — handles zip extraction, EXIF fixing, and SFTP upload |
| `google-photos-to-nas.html` | Browser wizard UI — served automatically by the Python server |

Both files must be in the **same folder**.

---

## Quick start

### Step 1 — Request your Google Takeout

1. Go to [takeout.google.com](https://takeout.google.com)
2. Click **Deselect all**, then tick only **Google Photos**
3. Click **Next step** → delivery: *Send download link via email* → format: `.zip` → size: **50 GB**
4. Click **Create export** and wait for Google's email (can take hours or days for large libraries)
5. Download all `.zip` files from the email into one folder on your computer — keep them zipped

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

1. **Guide** — pre-flight checklist (shown on first launch)
2. **Zip folder** — paste the path to your Takeout download folder and click Scan
3. **NAS setup** — enter your NAS IP, SSH port (default 22), username, password, and destination path
4. **Options** — toggle deduplication, EXIF restoration, skip-existing, and folder structure
5. **Transfer** — live log and progress bar while files upload
6. **Done** — summary and next steps

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

**Tip:** Use the **Test SFTP connection** button on the NAS setup screen. It will connect, verify the path, and confirm write access before you start the full transfer. If the path is wrong, it shows exactly what it can see so you can correct it.

If you see `SFTP cwd='/', root listing: ['Photos']` in the error, your session is chrooted to your home folder — use `Photos` as the destination path, or change the SFTP root in DSM → Control Panel → File Services → FTP → Advanced Settings.

---

## EXIF metadata restoration

Google Takeout strips the original date and GPS location from photo files and stores them separately in `.json` sidecar files. Without restoration, all your photos appear to have been taken on the day you exported them.

The wizard handles all Google's sidecar naming formats:

| Photo file | Sidecar Google creates |
|------------|------------------------|
| `photo.jpg` | `photo.jpg.json` or `photo.json` |
| `photo(1).jpg` | `photo(1).jpg.json` |
| Long filenames | Truncated to 46 characters |
| Some exports | `photo.jpg.supplemental-metadata.json` |

What gets restored per file type:

| Format | Date Taken | GPS coordinates | File modified time | Extended metadata |
|--------|-----------|-----------------|-------------------|------------------|
| JPEG / JPG | ✅ EXIF embedded | ✅ EXIF embedded | ✅ | ✅ description, keywords, orientation, people |
| PNG | ✅ tEXt chunk | — | ✅ | ✅ description, keywords, orientation, people |
| TIFF | ✅ Pillow required | ✅ Pillow required | ✅ | ✅ description, orientation |
| HEIC / HEIF | ⚠ Logged, needs manual tool | — | ✅ | — |
| Video (MP4, MOV, etc.) | ✅ ffmpeg required | ✅ ffmpeg required | ✅ | — |

Extended metadata includes descriptions/captions, album keywords, EXIF orientation, and people/face tag data from Google's JSON sidecars.

For HEIC files, the wizard logs which files need attention — you can use [ExifTool](https://exiftool.org) afterwards to fix those if needed.

For TIFF and video metadata, install the optional packages: `pip install pillow ffmpeg-python`.

---

## Folder structure options

| Option | Result on NAS |
|--------|--------------|
| Year / Month | `GooglePhotos/2022/06/photo.jpg` |
| Year only | `GooglePhotos/2022/photo.jpg` |
| Flat | `GooglePhotos/photo.jpg` |

---

## Troubleshooting

**"Access Denied" on upload**
- Check DSM → Control Panel → Shared Folder → Edit → Permission tab — your user needs Read/Write
- Make sure the path uses `/volume1/...` not `/photo/...` — unless you're chrooted (see NAS destination path section above)

**"Authentication failed"**
- Double-check your DSM username and password
- Make sure SSH is enabled in DSM → Control Panel → Terminal & SNMP → Enable SSH service

**"Folder not found" on scan**
- Windows: use backslashes — `C:\Users\You\Downloads\Takeout`
- macOS/Linux: use forward slashes — `/Users/you/Downloads/Takeout`
- Copy the path directly from your file manager to avoid typos

**`python` command not found (macOS/Linux)**
- Try `python3 sftp-run.py` instead
- On macOS you may need to install Python via [python.org](https://python.org) or `brew install python`

**`pip` command not found**
- Try `pip3 install paramiko piexif`
- On Linux: `sudo apt install python3-pip` then retry

**Browser doesn't open automatically**
- Manually open `http://localhost:8000` in your browser

**Transfer interrupted**
- Just run the wizard again with the same settings — with *Skip already-uploaded files* enabled it will resume from where it left off without re-uploading anything

**EXIF not restored on some files**
- The wizard logs `No sidecar found for: filename.jpg` when Google didn't include a JSON for that file
- This can happen with photos synced from other apps — the original date may already be embedded in the file

**Video metadata not embedded**
- Install the optional package: `pip install ffmpeg-python`
- If already installed and still not working, check the terminal for ffmpeg errors

**TIFF metadata not embedded**
- Install the optional package: `pip install pillow`

---

## After the transfer

1. Open **Synology Photos** on your NAS — your library will be indexed automatically
2. Install the **Synology Photos** app on your phone (Android / iOS) and enable auto-backup so new photos go straight to the NAS going forward
3. Once you've verified everything looks correct on the NAS, delete the Takeout zip files from your computer to free up space
4. You can now disable SSH on the NAS again: DSM → Control Panel → Terminal & SNMP → uncheck *Enable SSH service*
5. Consider cancelling your Google One subscription if you were paying for extra storage

---

## Dependencies

| Package | Purpose | Required |
|---------|---------|---------|
| `paramiko` | SFTP connection to Synology NAS | ✅ Required |
| `piexif` | Read and write EXIF metadata in JPEG/TIFF files | ✅ Required |
| `ffmpeg-python` | Embed metadata into video files | Optional |
| `pillow` | Embed metadata into TIFF files | Optional |

Install required packages: `pip install paramiko piexif`

Install all packages including optional: `pip install paramiko piexif ffmpeg-python pillow`

(Use `pip3` on macOS/Linux if `pip` is not found.)
