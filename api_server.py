"""Local web API for the CCTV gender and footfall pipeline."""

import json
import re
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import connect, init_db
from routes import add_footfall, router

ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
OUTPUT_DIR = RUNTIME_DIR / "outputs"
for directory in (UPLOAD_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="CCTV Analytics API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_db()
app.include_router(router)


@app.middleware("http")
async def no_cache_frontend(request, call_next):
    """Always revalidate the UI files so a rebuilt frontend is never masked by the browser cache."""
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response
jobs = {}
jobs_lock = threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def update_job(job_id, **changes):
    with jobs_lock:
        jobs[job_id].update(changes, updated_at=now())


def record_footfall(summary, location_id, job_id):
    """Feed a finished analysis into the retail analytics tables."""
    with connect() as db:
        add_footfall(db, {"location_id": location_id, "total": summary.get("footfall", 0), "male": summary.get("male", 0), "female": summary.get("female", 0), "source_job": job_id})


def run_pipeline(job_id, input_path, output_path, options):
    summary_path = output_path.with_suffix(".json")
    browser_output_path = output_path.with_name(f"{output_path.stem}_browser.mp4")
    command = [sys.executable, "-u", str(ROOT / "gender_video_pipeline.py"), "--video", str(input_path), "--output", str(output_path), "--summary", str(summary_path), "--yolo-model", options["yolo_model"], "--gender-model", str(ROOT / "gender_models" / "pa100k_yolov8n_cls.pt"), "--conf", str(options["confidence"]), "--classify-every", str(options["classify_every"]), "--entry-direction", options["entry_direction"], "--imgsz", "960", "--min-w", "12", "--min-h", "24"]
    update_job(job_id, status="processing", progress=0, message="Loading models")
    try:
        last_output = ""
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in process.stdout:
            line = line.strip()
            if line:
                last_output = line[:200]
            frame_match = re.search(r"Processed (\d+)/(\d+) frames", line)
            if frame_match:
                current, total = map(int, frame_match.groups())
                update_job(job_id, progress=round(current / total * 100) if total else 0, message=f"Processed {current:,} of {total:,} frames")
            elif line:
                update_job(job_id, message=line[:200])
        if process.wait() != 0:
            raise RuntimeError("The pipeline exited with an error. Check the server log for details.")
        if not output_path.is_file():
            raise RuntimeError("The pipeline completed without creating an output video.")
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg is required to prepare browser-compatible video playback.")
        update_job(job_id, message="Preparing browser-compatible video")
        conversion = subprocess.run(
            ["ffmpeg", "-y", "-i", str(output_path), "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(browser_output_path)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if conversion.returncode != 0 or not browser_output_path.is_file():
            raise RuntimeError("FFmpeg could not create a browser-compatible output video.")
        with summary_path.open(encoding="utf-8") as summary_file:
            summary = json.load(summary_file)
        record_footfall(summary, options.get("location_id"), job_id)
        update_job(job_id, status="completed", progress=100, message="Analysis complete", summary=summary, output_path=str(browser_output_path), output_url=f"/api/jobs/{job_id}/video")
    except Exception as exc:
        detail = f"{exc}: {last_output}" if last_output and str(exc) == "The pipeline exited with an error. Check the server log for details." else str(exc)
        update_job(job_id, status="failed", progress=0, message=detail)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cctv-analytics"}


@app.get("/api/jobs")
def list_jobs():
    with jobs_lock:
        return {"jobs": list(reversed(list(jobs.values())))}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/video")
def get_video(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "completed":
        raise HTTPException(status_code=404, detail="Output video is not ready")
    path = Path(job["output_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Output video not found")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.post("/api/jobs", status_code=202)
async def create_job(video: UploadFile = File(...), yolo_model: str = "yolov8m.pt", confidence: float = 0.28, classify_every: int = 1, location_id: int | None = None):
    if not video.filename or not video.filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="Upload an MP4, AVI, MOV, or MKV video")
    if yolo_model not in {"yolov8n.pt", "yolov8s.pt", "yolov8m.pt"} or not 0 < confidence <= 1 or classify_every < 1:
        raise HTTPException(status_code=400, detail="Invalid analysis options")
    job_id = uuid.uuid4().hex[:12]
    input_path = UPLOAD_DIR / f"{job_id}{Path(video.filename).suffix.lower()}"
    output_path = OUTPUT_DIR / f"{job_id}_annotated.mp4"
    with input_path.open("wb") as target:
        while chunk := await video.read(1024 * 1024):
            target.write(chunk)
    job = {"id": job_id, "filename": video.filename, "status": "queued", "progress": 0, "message": "Queued for analysis", "summary": None, "output_url": None, "output_path": str(output_path), "created_at": now(), "updated_at": now()}
    with jobs_lock:
        jobs[job_id] = job
    threading.Thread(target=run_pipeline, args=(job_id, input_path, output_path, {"yolo_model": yolo_model, "confidence": confidence, "classify_every": classify_every, "location_id": location_id, "entry_direction": "negative-to-positive"}), daemon=True).start()
    return job


app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")