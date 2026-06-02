1| # Photos → NAS Transfer Wizard
2| 
3| Move your entire Google Photos library to a Synology NAS — with full EXIF metadata restoration, deduplication, and automatic folder organisation.
4| 
5| ---
6| 
7| ## What you get
8| 
9| - Extracts all Google Takeout `.zip` files directly (no manual unzipping)
10| - Restores correct **date taken** and **GPS location** into each JPEG/PNG from Google's JSON sidecar files
11| - **Video metadata embedding** — embeds creation dates and GPS into MP4, MOV, AVI, MKV videos (requires ffmpeg-python)
12| - **Advanced HEIC/TIFF support** — restores metadata into HEIC (iPhone) and TIFF archival formats (requires Pillow)
13| - Extracts and embeds **photo descriptions, keywords, orientation, and face recognition tags** from Google metadata
13| - Sets the file's **modified timestamp** on the NAS to match the original photo date
14| - **Deduplicates** photos (Google Takeout often exports the same photo twice when it appears in multiple albums)
15| - Organises photos into **Year / Month** folders on the NAS automatically
16| - Skips files already on the NAS so it's safe to re-run after an interruption
17| - Live progress log in the browser with separate tracking for photos vs videos
18| 
19| ---
20| 
21| ## Requirements
22| 
23| ### On your computer
24| 
25| Python 3.8 or later is required on all platforms. Install the base dependencies once:
26| 
26| ```
27| pip install paramiko piexif
28| ```
29| 
30| **Optional dependencies** (for advanced metadata handling):
31| 
31| ```
32| pip install ffmpeg-python pillow
33| ```
34| 
35| - `ffmpeg-python` — required for embedding metadata into video files (MP4, MOV, AVI, MKV)
36| - `pillow` — required for HEIC and TIFF metadata embedding
36| - FFmpeg binary — download from [ffmpeg.org](https://ffmpeg.org/download.html) if you want video metadata support
37| 
38| #### Windows
39| 
40| - Download Python from [python.org](https://python.org) if not already installed — tick **"Add Python to PATH"** during setup
41| - Run the wizard from **PowerShell** or **Command Prompt**
42| - Paste zip folder paths using backslashes: `C:\Users\You\Downloads\Takeout`
43| - For video metadata: download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin` folder to your PATH
44| 
45| #### macOS
46| 
47| - Python 3 is available via [python.org](https://python.org) or Homebrew (`brew install python`)
48| - Run the wizard from **Terminal**
49| - Paste zip folder paths using forward slashes: `/Users/you/Downloads/Takeout`
50| - If `pip` is not found, try `pip3 install paramiko piexif`
51| - For video metadata: install FFmpeg via `brew install ffmpeg`
52| 
53| #### Linux
54| 
55| - Python 3 is pre-installed on most distributions. If not: `sudo apt install python3 python3-pip` (Debian/Ubuntu) or `sudo dnf install python3` (Fedora)
56| - Run the wizard from your **terminal**
57| - Paste zip folder paths using forward slashes: `/home/you/Downloads/Takeout`
58| - If pip is not found: `sudo apt install python3-pip`
59| - For video metadata: install FFmpeg via `sudo apt install ffmpeg` (Debian/Ubuntu)
60| 
61| ### On your Synology NAS
62| 
63| - **SFTP enabled** — DSM → Control Panel → File Services → FTP tab → SFTP section → tick *Enable SFTP service* → Apply
64| - Your DSM user must have **Read/Write** permission on the destination shared folder — DSM → Control Panel → Shared Folder → select folder → Edit → Permission tab
65| 
66| ---
67| 
68| ## Files
69| 
70| | File | Purpose |
71| |------|---------|
72| | `sftp-run.py` | Python backend server — handles zip extraction, EXIF fixing, video metadata, and SFTP upload |
73| | `google-photos-to-nas.html` | Browser wizard UI — served automatically by the Python server |
74| 
75| Both files must be in the **same folder**.
76| 
77| ---
78| 
79| ## Quick start
80| 
81| ### Step 1 — Request your Google Takeout
82| 
83| 1. Go to [takeout.google.com](https://takeout.google.com)
84| 2. Click **Deselect all**, then tick only **Google Photos**
85| 3. Click **Next step** → delivery: *Send download link via email* → format: `.zip` → size: **50 GB**
86| 4. Click **Create export** and wait for Google's email (can take hours or days for large libraries)
87| 5. Download all `.zip` files from the email into one folder on your computer — keep them zipped
88| 
89| > **Note:** Your Takeout will often be 1.5–2× larger than your Google storage shows, because photos that appear in multiple albums are exported multiple times. The wizard deduplicates them automatically.
90| 
91| ### Step 2 — Run the wizard
92| 
93| Open a terminal (or PowerShell on Windows) in the folder containing the two files and run:
94| 
95| ```
96| python sftp-run.py
97| ```
98| 
99| On macOS/Linux, if `python` isn't found, try:
100| 
101| ```
102| python3 sftp-run.py
103| ```
104| 
105| Your browser will open automatically at `http://localhost:8000`. Keep the terminal window open during the transfer.
106| 
107| ### Step 3 — Follow the wizard
108| 
109| The wizard walks you through 6 steps:
110| 
111| 1. **Guide** — pre-flight checklist (shown on first launch)
112| 2. **Zip folder** — paste the path to your Takeout download folder and click Scan
113| 3. **NAS setup** — enter your NAS IP, SSH port (default 22), username, password, and destination path
114| 4. **Options** — toggle metadata fixing, deduplication, skip-existing, and folder structure. Video metadata requires ffmpeg-python.
115| 5. **Transfer** — live log and progress bar while files upload. Separate counters for photos vs videos.
116| 6. **Done** — summary and next steps
117| 
118| ---
119| 
120| ## Finding the zip folder path
121| 
122| | Platform | How to get the path |
123| |----------|-------------------|
124| | **Windows** | Open the folder in File Explorer → click the address bar → copy the path (e.g. `C:\Users\Collins\Downloads\Takeout`) |
125| | **macOS** | Right-click the folder in Finder → hold Option → click *Copy "Takeout" as Pathname* (e.g. `/Users/collins/Downloads/Takeout`) |
126| | **Linux** | Right-click the folder in your file manager → Properties, or run `pwd` in the terminal after `cd`-ing into it |
127| 
128| ---
129| 
130| ## NAS destination path
131| 
132| The destination path must be the **real disk path** visible over SFTP, not the DSM display name.
133| 
134| | What you see in DSM | What to enter in the wizard |
135| |---------------------|-----------------------------|
136| | Shared folder `GooglePhotos` at `/volume1/GooglePhotos` | `Photos` *(if SFTP is chrooted to your home)* or `/volume1/GooglePhotos` |
137| | Shared folder `photo` at `/volume1/photo` | `/volume1/photo/GooglePhotos` |
138| 
139| **Tip:** Use the **Test SFTP connection** button on the NAS setup screen. It will connect, verify the path, and confirm write access before you start the full transfer. If the path is wrong, it will show diagnostic info.
140| 
141| If you see `SFTP cwd='/', root listing: ['Photos']` in the error, your session is chrooted to your home folder — use `Photos` as the destination path, or change the SFTP root in DSM → Control Panel → User → Edit → Home folder.
142| 
143| ---
144| 
145| ## Metadata restoration
146| 
147| Google Takeout strips the original date and GPS location from photo files and stores them separately in `.json` sidecar files. The wizard restores all this metadata automatically.
148| 
149| ### What gets restored per file type
150| 
151| | Format | Date Taken | GPS coordinates | Description | Keywords | Orientation | Face Tags |
152| |--------|-----------|-----------------|-------------|----------|-------------|-----------|
153| | JPEG / JPG | ✅ EXIF embedded | ✅ EXIF embedded | ✅ EXIF | ✅ EXIF | ✅ EXIF | ✅ User comment |
154| | PNG | ✅ tEXt chunk | — | ✅ tEXt | ✅ tEXt | ✅ tEXt | ✅ tEXt |
155| | HEIC / iPhone | ✅ EXIF | ✅ EXIF | ✅ EXIF | ✅ Keywords | ✅ Orientation | ⚠ Limited |
156| | TIFF / Archive | ✅ EXIF | ✅ EXIF | ✅ EXIF | ✅ Keywords | ✅ EXIF | ⚠ Limited |
157| | MP4 / MOV | ✅ creation_time | ⚠ format-limited | — | — | — | — |
158| | AVI / MKV | ✅ creation_time | ⚠ format-limited | — | — | — | — |
159| | Video (other) | — needs manual | — | — | — | — | — |
160| 
161| ### Technical notes
162| 
163| The wizard handles all Google's sidecar naming formats:
164| 
165| | Photo file | Sidecar Google creates |
166| |------------|------------------------|
166| | `photo.jpg` | `photo.jpg.json` or `photo.json` |
167| | `photo(1).jpg` | `photo(1).jpg.json` |
168| | Long filenames | Truncated to 46 characters |
169| | Some exports | `photo.jpg.supplemental-metadata.json` |
170| 
171| **Video metadata embedding** uses FFmpeg's lossless metadata injection (`-c copy` codec flags), so no re-encoding happens — videos transfer at full speed.
172| 
173| **HEIC/TIFF support** requires Pillow (PIL). If not installed, these formats will be skipped with a warning in the log.
174| 
175| ---
176| 
177| ## Troubleshooting
178| 
179| **"Access Denied" on upload**
180| - Check DSM → Control Panel → Shared Folder → Edit → Permission tab — your user needs Read/Write
180| - Make sure the path uses `/volume1/...` not `/photo/...` — unless you're chrooted (see NAS destination path section above)
181| 
182| **"Authentication failed"**
183| - Double-check your DSM username and password
184| - Make sure SFTP is enabled (not just SSH) in DSM → File Services → FTP → SFTP
185| 
186| **"Folder not found" on scan**
187| - Windows: use backslashes — `C:\Users\You\Downloads\Takeout`
188| - macOS/Linux: use forward slashes — `/Users/you/Downloads/Takeout`
189| - Copy the path directly from your file manager to avoid typos
190| 
191| **`python` command not found (macOS/Linux)**
192| - Try `python3 sftp-run.py` instead
193| - On macOS you may need to install Python via [python.org](https://python.org) or `brew install python`
194| 
195| **`pip` command not found**
196| - Try `pip3 install paramiko piexif` (and `ffmpeg-python pillow` for optional features)
196| - On Linux: `sudo apt install python3-pip` then retry
197| 
198| **Browser doesn't open automatically**
199| - Manually open `http://localhost:8000` in your browser
200| 
201| **Transfer interrupted**
202| - Just run the wizard again with the same settings — with *Skip already-uploaded files* enabled it will resume from where it left off without re-uploading anything
203| 
204| **EXIF not restored on some files**
205| - The wizard logs `No sidecar found for: filename.jpg` when Google didn't include a JSON for that file
206| - This can happen with photos synced from other apps — the original date may already be embedded in the file
207| - For videos without metadata, the wizard logs a warning; consider using external tools like ExifTool if manual tagging is needed
208| 
209| **ffmpeg not found (video metadata)**
210| - Install FFmpeg: Windows ([ffmpeg.org](https://ffmpeg.org/download.html)), macOS (`brew install ffmpeg`), Linux (`sudo apt install ffmpeg`)
210| - Verify it's in your PATH by running `ffmpeg -version` in terminal
211| - Without ffmpeg, the wizard will log warnings and skip video metadata
212| 
213| **Pillow import error (HEIC/TIFF)**
214| - Install Pillow: `pip install pillow` (or `pip3` on macOS/Linux)
214| - Without Pillow, HEIC and TIFF files will be transferred but metadata won't be embedded — log will show warnings
215| 
216| ---
217| 
218| ## After the transfer
219| 
220| 1. Open **Synology Photos** on your NAS — your library will be indexed automatically
221| 2. Install the **Synology Photos** app on your phone (Android / iOS) and enable auto-backup so new photos go straight to the NAS going forward
222| 3. Once you've verified everything looks correct on the NAS, delete the Takeout zip files from your computer to free up space
223| 4. Consider cancelling your Google One subscription if you were paying for extra storage
224| 
225| ---
226| 
227| ## Dependencies
228| 
229| | Package | Purpose | Required? |
230| |---------|---------|-----------|
230| | `paramiko` | SFTP connection to Synology NAS | **Yes** |
231| | `piexif` | Read and write EXIF metadata in JPEG files | **Yes** |
232| | `ffmpeg-python` | Embed metadata into video files | Optional — videos will be skipped if missing |
233| | `pillow` (PIL) | HEIC and TIFF metadata embedding | Optional — these formats will be skipped if missing |
234| | FFmpeg binary | Required by ffmpeg-python for video processing | Optional — only if you want video metadata |
235| 
236| Install core dependencies with: `pip install paramiko piexif`
237| 
237| Install all optional dependencies with: `pip install ffmpeg-python pillow`
238| 
239| (On macOS/Linux, use `pip3` if `pip` isn't in your PATH)
