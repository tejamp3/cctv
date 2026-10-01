# VS corp CCTV Retail Analytics

A local web dashboard and API for CCTV-based retail analytics. The working end-to-end
feature is **Video Analysis**: upload a recorded video, and the pipeline detects people
(YOLOv8), tracks them across frames, classifies each tracked person's gender with a
locally trained classifier, counts footfall across a line, and returns an annotated
video plus a demographic summary. The rest of the dashboard (cameras, DVR, audit,
tickets, FR attendance, etc.) is a full SPA + API scaffold for a retail CCTV product,
backed by a real SQLite database and real endpoints, but starts empty until data is
added — there is no seed/demo data.

## What's in this repo

```
api_server.py              FastAPI app: serves the frontend, runs analysis jobs, job polling endpoints
routes.py                  All /api/* REST endpoints (locations, cameras, recordings, events,
                            attendance, tickets, retail analytics)
database.py                SQLite schema + connection helpers (creates runtime/vscorp.db on first run)
gender_video_pipeline.py   Core CV pipeline: YOLOv8 person detection + tracking, gender
                            classification, line-crossing footfall counting
count_footfall.py          Standalone/earlier footfall-only line-crossing counter

frontend/                  Hash-routed single-page app (vanilla JS, no build step)
  index.html
  app.js                   All pages/routes, API calls, chart rendering
  styles.css                Layout + color palette

train_gender_classifier.py Train/continue-training the YOLOv8-classification gender model
prepare_pa100k.py          Build a YOLO ImageFolder dataset (male/female) from the PA-100K
                            pedestrian attribute dataset
wrn_gender.py               Alternate face-based gender/age model (WRN-16-8), not currently
                            wired into the pipeline — see its docstring for standalone usage
gender_models/              Trained checkpoints (pa100k_yolov8n_cls.pt is the one the API uses)

requirements.txt            Python dependencies
scope-of-work.md            Project scope/requirements document
cctv-analytics-architecture-detailed.md            Detailed architecture notes
cctv-analytics-highlevel-architecture-learning-guide.md   Architecture walkthrough for learning
jarvis-screenshots/         UI screenshots of each dashboard page
Deep_Learning_based_approach_to_detect_Customer_Age_Gender_and_Expression_in_Surveillance_Video.pdf
                            Reference paper the WRN face-gender model is based on
```

Not committed to git (regenerable or external — see `.gitignore`):
- `runtime/` — uploaded videos, annotated outputs, and `vscorp.db`; created automatically on first run
- `gender_dataset/` — the ~90k-image PA-100K training set; rebuild with `prepare_pa100k.py`
- `yolov8m.pt`, `yolov8n-cls.pt` — stock Ultralytics pretrained weights; auto-downloaded on first use
- sample/output `*.mp4` files

## Getting started — step by step (no coding experience needed)

This walks through everything from an empty Windows machine to the dashboard open in
your browser. It looks long because every step is spelled out — in practice it's about
15 minutes, most of it spent waiting for one install to finish. Steps 1–4 are one-time
setup; once they're done, starting the app again later is just step 7.

Every grey code block below is a command. Type or paste it into **PowerShell** (not
Command Prompt / `cmd.exe`) and press Enter, one block at a time, waiting for each to
finish before running the next.

### 1. Install Python

You need Python 3.10 or newer.

- Check if you already have it: open PowerShell (press the Windows key, type
  `powershell`, press Enter) and run:
  ```powershell
  python --version
  ```
  If that prints something like `Python 3.11.5`, skip to step 2.
- If it says `Python was not found` or shows a version older than 3.10, install Python
  from **python.org/downloads** (click the big "Download Python" button) or by running:
  ```powershell
  winget install Python.Python.3.12
  ```
  **Important:** if you use the python.org installer, tick the checkbox **"Add
  python.exe to PATH"** on the first screen before clicking Install.
- Close and reopen PowerShell after installing, then re-run `python --version` to
  confirm it works.

### 2. Install FFmpeg

The app uses a tool called FFmpeg to make the processed videos playable in a browser.
Without it, video analysis will fail with an FFmpeg error.

```powershell
winget install Gyan.FFmpeg
```

Close and reopen PowerShell, then confirm it worked:

```powershell
ffmpeg -version
```

You should see a version number printed, not an error. (If `winget` itself isn't
recognized, update Windows via Settings → Windows Update, or download FFmpeg manually
from **gyan.dev/ffmpeg/builds** and follow their instructions to add it to your PATH.)

### 3. Get the project files onto your machine

If you were sent a link to this GitHub repository:

```powershell
git clone https://github.com/tejamp3/cctv.git
cd cctv
```

(If `git` isn't recognized, install it from **git-scm.com/downloads**, or simpler: on
the GitHub page click the green **Code** button → **Download ZIP**, then right-click the
downloaded file → **Extract All**.)

### 4. Open a terminal inside the project folder

Every command from here on must be run **from inside the project folder** (the one that
contains `api_server.py`). The easiest way:

1. Open the project folder in File Explorer.
2. Click once in the empty area of the address bar at the top, type `powershell`, and
   press Enter. A PowerShell window opens already pointed at that folder.

(If you used `git clone` in step 3, you're already there after the `cd cctv` command.)

### 5. Create a private Python environment for this project (one-time)

This keeps the project's dependencies separate from anything else on your computer:

```powershell
python -m venv venv
```

This creates a `venv` folder inside the project. You'll see nothing print out if it
worked — that's normal.

### 6. Install the project's dependencies (one-time, takes a few minutes)

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

This downloads everything the project needs (the web server, the AI/computer-vision
libraries, etc.). It's a large download (a few GB, mostly the `torch` machine-learning
library) — on a normal connection this can take 5–15 minutes. Let it finish; lots of
text scrolling by is normal.

### 7. Start the application

```powershell
.\venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8765
```

Leave this window open — it's the running server. You'll see log lines appear; that
means it's working. (The very first time you analyze a video, it will also silently
download the YOLOv8 detection model from the internet in the background — a one-time,
~50MB download.)

### 8. Open the dashboard in your browser

Open a web browser and go to:

```
http://127.0.0.1:8765
```

You'll see a sign-in screen. **Type anything** in the email and password fields — this
is a local demo login that doesn't check against a real account, it just needs
something typed in.

### 9. Try it out

Click **Video Analysis** in the left sidebar, choose a store location (optional), and
either drag a video file onto the upload box or click it to browse for one (MP4, AVI,
MOV, or MKV). Click **Analyze footage**. You'll see a progress bar while it processes —
for a short video this is usually under a minute on a normal computer; longer videos or
older machines take longer. When it finishes, the annotated video (with boxes and
male/female labels drawn on each person) plays back, along with footfall and gender
counts below it.

### Stopping the app, and running it again later

- To stop the server, click into the PowerShell window running it and press
  **Ctrl+C**.
- Next time you want to use it, you only need to repeat **step 7** (and open
  `http://127.0.0.1:8765` again) — steps 1–6 don't need to be redone, since the
  environment and dependencies are already installed.

### Troubleshooting

- **`python : The term 'python' is not recognized...`** — Python isn't installed, or
  wasn't added to PATH. Reinstall from python.org and tick "Add python.exe to PATH", or
  run `winget install Python.Python.3.12`, then open a brand-new PowerShell window.
- **`running scripts is disabled on this system`** — Windows is blocking script
  execution. This project only uses `.\venv\Scripts\python.exe` directly, which isn't
  affected by this, so you shouldn't hit it following the steps above. If you do, run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` in PowerShell and confirm with
  `Y`.
- **`FFmpeg is required to prepare browser-compatible video playback`** (shown in the
  dashboard after an analysis fails) — FFmpeg isn't installed or isn't on PATH. Redo
  step 2, then fully close and reopen PowerShell (and restart the server) so it picks up
  the updated PATH.
- **It's stuck "Loading models" / downloading something** on the very first analysis —
  this is normal: it's downloading the ~50MB YOLOv8 detector the first time only. It
  needs an internet connection for this one-time download; after that it's cached
  locally.
- **`error: Microsoft Visual C++ 14.0 or greater is required`** during step 6 — a rare
  issue on very old Windows/Python combinations installing `torch`/`opencv`. Installing
  the latest Python 3.12 via `winget` (step 1) usually avoids this.
- **The browser shows nothing / "can't connect"** — make sure the PowerShell window
  from step 7 is still open and shows no error, and that you typed the address exactly
  as `http://127.0.0.1:8765` (not `https`).
- **Port already in use** — something else is already using port 8765. Either close
  whatever that is, or start this app on a different port, e.g. add `--port 8766` to the
  step 7 command and open `http://127.0.0.1:8766` instead.

## Run the dashboard (quick reference)

Once steps 1–6 above are done, starting the app is always just:

```powershell
.\venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` in a browser. Sign in with any email/password (the login is
a local placeholder — it doesn't check credentials against anything). Go to **Video
Analysis** in the sidebar, upload an MP4/AVI/MOV/MKV file, and watch it process.

Uploaded videos, annotated outputs, and the SQLite database all live under `runtime/`,
created the first time the server starts. Analysis jobs are tracked in memory, so
restarting the server clears the job list (the output files on disk are unaffected).

## Prerequisites (summary)

- **Python 3.10+** — see step 1 above.
- **FFmpeg on PATH** — see step 2 above. Required or every analysis job fails.
- **Internet access** the first time you run an analysis, so Ultralytics can
  auto-download `yolov8m.pt` (the person detector; not stored in this repo). On a
  permanently offline machine, place a copy of `yolov8m.pt` in the project root
  yourself beforehand.
- A CUDA-capable GPU is optional — everything runs on CPU, just slower (training and
  video analysis both fall back to CPU automatically if no GPU is available).

## How the video analysis pipeline works

1. **Detection** — YOLOv8 (`yolov8m.pt` by default) finds people in each frame.
2. **Tracking** — Ultralytics' built-in tracker follows each detected person across
   frames so they're counted once, not once per frame.
3. **Gender classification** — every `--classify-every` frames, each tracked person's
   crop is classified male/female by the locally trained model at
   `gender_models/pa100k_yolov8n_cls.pt`.
4. **Footfall counting** — a horizontal line at 40% of the frame height; a tracked
   person is counted when their path crosses it in the configured direction.
5. **Output** — an annotated video (boxes + labels), a JSON summary (footfall, male/female
   counts, tracked people), and — if a store location was selected — the summary is
   written into the retail analytics tables so it shows up under **Retail Analytics**.

You can also run the pipeline directly from the command line without the API/UI:

```powershell
.\venv\Scripts\python.exe gender_video_pipeline.py --video path\to\video.mp4 --output out.mp4 --summary out.json
```

Run `python gender_video_pipeline.py --help` for all options (confidence threshold,
classify-every-N-frames, line position/direction, detection resolution, etc.).

## API endpoints

All under `/api`. Grouped by area:

| Area | Endpoints |
|---|---|
| Health | `GET /health` |
| Video analysis | `POST /jobs` (upload+start), `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/video` |
| Locations | `GET/POST /locations`, `PUT/DELETE /locations/{id}` |
| Cameras | `GET/POST /cameras`, `GET /cameras/summary`, `GET/PATCH/DELETE /cameras/{id}`, `POST /cameras/{id}/heartbeat`, `GET /cameras/{id}/snapshot` |
| Recordings (DVR) | `GET/POST /recordings`, `GET /recordings/{id}/video` |
| Events / audit | `GET/POST /events`, `GET /events/types`, `GET /events/export`, `GET /events/summary`, `GET /events/stats`, `PATCH/DELETE /events/{id}` |
| Employees / FR attendance | `GET/POST /employees`, `DELETE /employees/{id}`, `POST /attendance/clock`, `GET /attendance`, `GET /attendance/{id}/logs`, `GET /attendance/report` |
| Tickets | `GET/POST /tickets`, `GET /tickets/summary`, `GET/PATCH/DELETE /tickets/{id}` |
| Retail analytics | `POST /retail/footfall`, `GET /retail/summary`, `GET /retail/heatmap`, `GET /retail/timeseries`, `GET /retail/age`, `GET /retail/dwell` |

The frontend (`frontend/app.js`) calls these directly; there's no separate API docs
page, but the handler signatures in `routes.py` are the source of truth for params.

## Training / improving the gender classifier

The shipped model (`gender_models/pa100k_yolov8n_cls.pt`) is a YOLOv8-nano classifier
trained on the PA-100K pedestrian dataset (full-body crops, not faces). Current
validation accuracy is **~0.70 top-1** — usable for rough demographic splits, not
forensic-grade per-person accuracy. `gender_models/` also keeps earlier checkpoints
(`*.3epoch_0.701.pt`, `*.5epoch_0.696.pt`, `*.backup.pt`) for comparison/rollback.

To rebuild the dataset and retrain from scratch:

```powershell
.\venv\Scripts\python.exe prepare_pa100k.py          # downloads PA-100K, writes gender_dataset/pa100k/{train,val}/{male,female}
.\venv\Scripts\python.exe train_gender_classifier.py --epochs 30 --device cpu   # or --device 0 for CUDA
```

Key flags on `train_gender_classifier.py`: `--epochs`, `--batch`, `--imgsz`, `--fraction`
(use a subset of the data for a quick test run), `--model` (start from a different
checkpoint, e.g. to continue training). Ultralytics writes each run to
`runs/gender/pa100k_yolov8n_cls*/weights/{best,last}.pt` (outside this repo by default —
copy the one you want to use into `gender_models/pa100k_yolov8n_cls.pt` to make the API
pick it up).

Because PA-100K is body-crop CCTV-style data, it's a reasonable match for this use case,
but accuracy plateaus around 0.70–0.72 on the nano backbone regardless of epoch count —
more epochs alone won't reach significantly higher accuracy. See
`wrn_gender.py` for a face-based alternative (gender from a detected face rather than
full body), which tends to be more accurate when faces are clearly visible, and is
documented separately in its own module docstring.

## Known limitations

- **No seed data.** Cameras, DVR, tickets, FR attendance, and most of Retail Analytics
  will show empty states until you create data through the API — only Video Analysis
  (and whatever it writes into Retail Analytics) works out of the box.
- **Login is not real authentication** — any email/password combination signs in.
- **Gender accuracy is ~0.70**, trained on full-body CCTV-style crops, not faces.
- **FFmpeg and internet access** are required the first time you run an analysis (see
  Prerequisites above).
- Analysis jobs are **in-memory only** — restarting the server loses the job list
  (though output files remain in `runtime/outputs/`).

## Further reading

- `scope-of-work.md` — original project scope and requirements
- `cctv-analytics-architecture-detailed.md` — detailed architecture notes
- `cctv-analytics-highlevel-architecture-learning-guide.md` — architecture walkthrough
- `jarvis-screenshots/` — screenshots of every dashboard page
