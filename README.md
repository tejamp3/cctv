# CCTV Analytics Dashboard

This workspace now includes a local web UI for uploading a recorded video, running the existing YOLOv8 + gender pipeline, and viewing the annotated output with footfall and gender counts. Automatic line calibration analyzes tracked movement and chooses an angled boundary with the strongest distinct crossings.

## Run locally

From this folder, use the project environment and install the dependencies:

```powershell
& .\venv\Scripts\python.exe -m pip install -r requirements.txt
& .\venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` in a browser. Uploaded videos and generated results are stored under `runtime/`.

The first analysis downloads `NTQAI/pedestrian_gender_recognition` through Transformers. The dashboard polls these endpoints while a job is running:

- `POST /api/jobs` - upload and start an analysis job
- `GET /api/jobs` - list jobs in the current server session
- `GET /api/jobs/{job_id}` - read job status, progress, and summary counts
- `GET /api/jobs/{job_id}/video` - stream the annotated result
- `GET /api/health` - service health check

This is a local batch-processing UI. Jobs are held in memory, so restarting the API clears the job list, while files remain in `runtime/`.

The dashboard uses a fixed horizontal counting line at 40% of the frame height. Automatic line calibration is disabled. Gender analysis uses the local PA-100K-trained YOLOv8-nano classifier at `gender_models/pa100k_yolov8n_cls.pt`.

The API uses FFmpeg after analysis to convert OpenCV's output into H.264 with browser-compatible pixel format, so the annotated result can play directly in the dashboard.