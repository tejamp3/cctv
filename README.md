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

## Prerequisites

1. **Python 3.10+** with a virtual environment (the setup below assumes a `venv/` folder
   next to this README; create one with `python -m venv venv` if it doesn't exist).
2. **FFmpeg installed and on your PATH.** The API shells out to `ffmpeg` after every
   analysis job to convert the annotated video to browser-compatible H.264 — without it,
   every job fails with *"FFmpeg is required to prepare browser-compatible video
   playback."*
   - Windows: `winget install Gyan.FFmpeg` (or download from gyan.dev and add `ffmpeg/bin`
     to PATH), then open a new terminal.
   - Verify with `ffmpeg -version`.
3. **Internet access on first run.** `yolov8m.pt` (the person detector) is not stored in
   this repo and is downloaded automatically by Ultralytics the first time it's needed.
   On an offline machine, place a copy of `yolov8m.pt` in the project root yourself
   before running an analysis.
4. A CUDA-capable GPU is optional — everything runs on CPU, just slower (training and
   video analysis both fall back to CPU automatically if no GPU is available).

## Run the dashboard

From this folder, in PowerShell:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` in a browser. Sign in with any email/password (the login is
a local placeholder — it doesn't check credentials against anything). Go to **Video
Analysis** in the sidebar, upload an MP4/AVI/MOV/MKV file, and watch it process.

Uploaded videos, annotated outputs, and the SQLite database all live under `runtime/`,
created the first time the server starts. Analysis jobs are tracked in memory, so
restarting the server clears the job list (the output files on disk are unaffected).

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
