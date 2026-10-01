# High-Level Architecture — Deep Dive, Tech Stack & Learning Resources
**Companion document to:** Retail CCTV Analytics — Detailed Architecture, Tech Stack & Implementation Plan
**Purpose of this document:** Expand Section 2 (High-Level Architecture) into a stage-by-stage learning guide — what each stage does, the concrete technology choice, and where to actually go to learn it (official docs, a hands-on tutorial, and a real example project for each).

---

## 1. The Architecture, Recapped

```
[DVR/NVR] → [Ingestion Layer] → [Preprocessing] → [Queue] → [ML Inference] → [DB/Storage] → [API] → [Dashboard]
```

Each arrow above is a service boundary you'll actually build and test independently. The sections below walk the pipeline left to right, and for every stage give you three things:

1. **What it does and why it's there**
2. **Official documentation** — the authoritative reference
3. **A tutorial or example project** — something you can actually run to see the concept work

This is written so a developer new to any one of these pieces (video pipelines, queues, ML serving, dashboards) has a concrete starting point rather than just a technology name.

---

## 2. Stage 1 — Ingestion Layer

**What it does:** Pulls frames out of the DVR/NVR, either as a continuous RTSP stream or by watching a folder for exported files, and hands raw frames downstream — regardless of camera brand.

### RTSP stream capture

| | |
|---|---|
| **Why RTSP** | It's the near-universal protocol IP cameras and DVR/NVRs use to expose a live video feed over the network |
| **Tech choice** | FFmpeg (as a subprocess) or OpenCV's `VideoCapture` with the FFmpeg backend |
| **Official docs** | [FFmpeg documentation](https://ffmpeg.org/documentation.html) · [OpenCV `VideoCapture` class reference](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html) |
| **Tutorial to learn from** | [mpolinowski/opencv-rtsp](https://github.com/mpolinowski/opencv-rtsp) — a short, runnable walkthrough of opening an RTSP stream in Python with OpenCV, including the environment variable workaround for stream-transport issues |
| **Worth knowing before you build** | RTSP streams drop connections; production code needs a reconnect loop with backoff, not just a bare `while True: cap.read()`. Search the OpenCV GitHub issues for "RTSP" if you hit a hang — this is a well-documented rough edge, not something you're doing wrong |

### File-export fallback

| | |
|---|---|
| **Why it exists** | Some DVR/NVR units only support scheduled export to a folder/FTP share rather than live RTSP — this path keeps the pipeline brand-agnostic |
| **Tech choice** | Python's `watchdog` library (filesystem event notifications) |
| **Official docs** | [python-watchdog documentation](https://python-watchdog.readthedocs.io/) |
| **Tutorial to learn from** | The "Quickstart" section of the watchdog docs above walks through watching a directory and reacting to new files in ~15 lines of code — directly transferable to "new file dropped by DVR export" |

---

## 3. Stage 2 — Preprocessing (Frame Extraction, Filtering, Dedup)

**What it does:** Turns a raw video stream into a clean, low-volume sequence of frames worth sending to the ML engine — extracting at 2–5 fps, dropping blank/dark frames, and removing near-duplicates.

| | |
|---|---|
| **Tech choice** | OpenCV for frame grabbing and resizing; simple frame-differencing or perceptual hashing (`pHash`) for dedup |
| **Official docs** | [OpenCV `VideoCapture.read()` / frame-handling docs](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html) (same reference as above — extraction and capture are the same API) |
| **Concept to learn** | Perceptual hashing for near-duplicate detection — search "pHash image deduplication Python" for the `imagehash` PyPI package, a small, well-documented library that does this in a few lines |
| **Why this matters for this project specifically** | The architecture doc's Section 3B calls this out as the first place to look if the ML engine ever becomes the bottleneck — an adaptive, motion-gated version of this stage (skip frames with near-zero pixel delta) is the cheapest lever you have before touching compute/GPU spend |

---

## 4. Stage 3 — Queue / Buffer

**What it does:** Decouples ingestion speed from ML processing speed so a momentarily slow model doesn't drop or block camera frames.

| | |
|---|---|
| **Tech choice** | Redis Streams |
| **Official docs** | [Redis Streams — data type introduction](https://redis.io/docs/latest/develop/data-types/streams/) · [Redis streaming use-case guide](https://redis.io/docs/latest/develop/use-cases/streaming/) |
| **What to actually learn** | Four commands cover 90% of this project's needs: `XADD` (producer pushes a frame reference), `XREADGROUP` (consumer group reads), `XACK` (mark processed), and `XLEN`/`MAXLEN` (bound the queue for backpressure). The Redis docs above walk through consumer groups and recovering from a crashed consumer — both directly relevant to a pipeline that must survive a restart without losing track of where it was |
| **Why Redis Streams over Kafka/RabbitMQ here** | Single binary, no cluster/partition management, and built-in trimming (`MAXLEN ~`) gives you the drop-oldest backpressure policy from Section 3C of the main architecture doc for free |

---

## 5. Stage 4 — ML Inference Engine

Your model stays a black box, but the pipeline is built around well-known, swappable methods for each sub-task. Learning any one of these independently will make the "black box" much less opaque when you're debugging integration issues.

### Person detection

| | |
|---|---|
| **Tech choice** | YOLOv8 (Ultralytics) |
| **Official docs** | [Ultralytics YOLO documentation](https://docs.ultralytics.com/) · [Predict mode reference](https://docs.ultralytics.com/modes/predict/) |
| **Tutorial to learn from** | The Ultralytics docs' own quickstart (`pip install ultralytics`, then a 5-line predict script) is the fastest path to a working detector on a sample video — deliberately designed to be copy-pasteable |

### Multi-object tracking (turns per-frame detections into unique-visitor counts)

| | |
|---|---|
| **Tech choice** | ByteTrack (fast, IoU-based, no re-identification) or DeepSORT (adds appearance-embedding re-ID, better through occlusion) |
| **Official docs / repos** | [Ultralytics track mode](https://docs.ultralytics.com/modes/track/) (ByteTrack and BoT-SORT are built in and selectable via a config flag) · [ByteTrack — original repo](https://github.com/ifzhang/ByteTrack) · [Deep SORT — original repo](https://github.com/nwojke/deep_sort) · [deep_sort_realtime — a maintained, frame-by-frame-friendly fork](https://github.com/levan92/deep_sort_realtime) · [Norfair — a lighter-weight, highly customizable tracker](https://github.com/tryolabs/norfair) |
| **Example projects to study end-to-end** | [SVSS13/Footfall-Counter](https://github.com/SVSS13/Footfall-Counter) — YOLOv8 + a custom centroid tracker + a virtual ROI line for IN/OUT counting; a very close match to this project's footfall use case. [Kerem-Kurt/YOLOv8-and-DEEPSORT-Human-Foot-Trafficker](https://github.com/Kerem-Kurt/YOLOv8-and-DEEPSORT-Human-Foot-Trafficker) — YOLOv8 + DeepSORT specifically for foot-traffic counting |
| **Why this stage matters most to get right** | Without tracking, "person count" over a video just counts detections per frame, which massively overcounts (the same shopper gets counted in every frame they appear in). Tracking is what turns raw detections into a defensible "unique visitors" metric |

### Demographic estimation (age/gender)

| | |
|---|---|
| **Tech choice** | DeepFace (easiest to get running) or InsightFace (more accurate, more setup) |
| **Official docs / repos** | [DeepFace — GitHub](https://github.com/serengil/deepface) · [InsightFace — GitHub](https://github.com/deepinsight/insightface) (project site: [insightface.ai](https://insightface.ai)) |
| **Tutorial to learn from** | DeepFace's own README example — `DeepFace.analyze(img_path=..., actions=['age','gender'])` — is a two-line starting point; it's a wrapper around several backbones so you can swap accuracy/speed trade-offs without rewriting your integration code |
| **Validate before trusting operationally** | Both libraries publish their benchmark accuracy on standard datasets, not on retail CCTV angles/lighting — the architecture doc's Section 8 flags this as a risk worth budgeting real-footage validation time for in Phase 3 |

### Attendance matching (the open decision from Section 5 of the main doc)

| | |
|---|---|
| **Face-recognition path** | Same DeepFace/InsightFace libraries above handle verification (`DeepFace.verify`) and 1:N search (`DeepFace.find` or InsightFace's embedding similarity) — this is what you'd build employee enrollment on top of |
| **Zone/dwell-time path** | No dedicated library — this is a geometry problem: define a polygon region in frame coordinates, check tracked centroids against it, and apply a minimum-dwell-time rule. Any tracker above already gives you the centroid trajectory you need; the "learning" here is really just the ROI-line logic used in the SVSS13/Footfall-Counter example above |

### Serving the model behind a stable contract

| | |
|---|---|
| **Tech choice** | A small FastAPI/Flask wrapper around ONNX Runtime (or TorchServe if staying in native PyTorch) |
| **Official docs** | [ONNX Runtime documentation](https://onnxruntime.ai/docs/) · [TorchServe documentation](https://pytorch.org/serve/) |
| **Tutorial to learn from** | [naxty/scikit-onnx-fastapi-example](https://github.com/naxty/scikit-onnx-fastapi-example) — small, complete example of exporting a model to ONNX and serving it behind FastAPI with `docker-compose up`; the pattern (load ONNX once at startup, expose a `/predict` POST endpoint) is exactly what you'd do for the detection/tracking/demographics model here, just with an image input instead of tabular data |

---

## 6. Stage 5 — Local Database

**What it does:** Stores every detection/demographic/attendance event as structured, queryable rows for the API and dashboard to read.

| | |
|---|---|
| **Tech choice** | PostgreSQL, optionally with the TimescaleDB extension for time-series-heavy footfall queries |
| **Official docs** | [PostgreSQL documentation](https://www.postgresql.org/docs/) · [TimescaleDB documentation](https://docs.timescale.com/) |
| **What to actually learn first** | Plain PostgreSQL — `CREATE TABLE`, indexes on `(camera_id, ts)`, and a basic `GROUP BY date_trunc('hour', ts)` query — covers the pilot's needs. Only reach for TimescaleDB's `hypertable` concept once you notice footfall queries over weeks/months slowing down; it's an incremental extension, not a different database to learn from scratch |

---

## 7. Stage 6 — Backend API

| | |
|---|---|
| **Tech choice** | FastAPI |
| **Official docs** | [FastAPI documentation](https://fastapi.tiangolo.com/) · [FastAPI tutorial — user guide](https://fastapi.tiangolo.com/tutorial/) |
| **What to actually learn** | The tutorial's first few pages (path operations, request/response models with Pydantic, and the auto-generated `/docs` page) are enough to build the three endpoints this pilot needs: live stats, historical/footfall trends, and attendance logs. The auto-generated interactive docs at `/docs` are worth knowing about early — they let you test each endpoint from a browser with zero extra tooling |

---

## 8. Stage 7 — Dashboard

**What it does:** Turns the data in Postgres into something a store manager can actually look at.

| | |
|---|---|
| **Tech choice (recommended)** | Grafana, pointed directly at PostgreSQL, per Section 3H of the main architecture doc |
| **Official docs** | [Grafana PostgreSQL data source docs](https://grafana.com/docs/grafana/latest/datasources/postgres/) |
| **Tutorial to learn from** | [TimescaleDB's Grafana connection tutorial](https://docs.timescale.com/tutorials/latest/grafana/) — walks through adding Postgres/Timescale as a data source and building a first time-series panel; directly transferable even if you don't end up using the TimescaleDB extension itself |
| **If a custom React dashboard is needed instead** | This only applies to the small admin-action pages (e.g., correcting an attendance match) that Grafana can't do — for those, plain React + Recharts against the FastAPI endpoints above is enough; no dedicated tutorial needed beyond the FastAPI docs already listed |

---

## 9. Stage 8 — Deployment & Infrastructure

| Piece | Tech choice | Official docs | Tutorial / example |
|---|---|---|---|
| Orchestration | Docker Compose | [Docker Compose — getting started](https://docs.docker.com/compose/gettingstarted/) | [docker/awesome-compose](https://github.com/docker/awesome-compose) — a library of real multi-service Compose examples (web app + Redis + Postgres is one of them, almost exactly this project's shape) |
| Reverse proxy / TLS | Nginx | [Nginx reverse proxy admin guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/) | The admin guide's own worked example (`proxy_pass` in front of a backend on a different port) is a direct match for putting Nginx in front of the FastAPI + Grafana services |
| Monitoring | Prometheus (+ reuse the Grafana instance) | [Prometheus — first steps](https://prometheus.io/docs/introduction/first_steps/) | The "first steps" guide has Prometheus monitoring itself as the very first example — good enough to understand scrape configs before pointing it at your own services |
| Object storage (optional, snapshot upgrade path) | MinIO | [MinIO documentation](https://min.io/docs/) · [MinIO — GitHub](https://github.com/minio/minio) | The README's own Docker quickstart (`docker run ... minio/minio server /data`) gets a local S3-compatible bucket running in under a minute — useful to have in your back pocket for the multi-store upgrade path noted in Section 9 of the main doc |

---

## 10. Suggested Learning Order (if the stack is new to you)

You don't need to learn everything before starting Phase 1. This is roughly the order that matches how the phases in the main architecture doc actually get built:

1. **OpenCV + FFmpeg basics** (Stage 1–2) — get a single RTSP camera or sample video file producing a folder of extracted frames. This alone validates the hardest "does this even connect" risk early.
2. **Redis Streams** (Stage 3) — push those extracted frames onto a stream and consume them with a second script. Small, self-contained, teaches the producer/consumer pattern you'll reuse everywhere.
3. **YOLOv8 + a tracker** (Stage 4) — run the Ultralytics quickstart on a sample video, then layer in ByteTrack via the built-in `track` mode. Compare against the SVSS13/Footfall-Counter example to see a complete "detect → track → count" loop.
4. **FastAPI + Postgres** (Stage 6–5) — build the three endpoints against a hand-seeded table before wiring in real ML output; this de-risks the API/DB layer independently of the ML pipeline being finished.
5. **Grafana against Postgres** (Stage 7) — once real rows are landing in the DB, this is usually the fastest, most satisfying stage to build — a working dashboard often takes hours, not days.
6. **Docker Compose + Nginx** (Stage 8) — wrap everything built above into one `docker compose up`, using an `docker/awesome-compose` example as your starting template rather than writing the Compose file from scratch.

---

## 11. Consolidated Resource Table

| Stage | Technology | Official Docs | Tutorial | Example Project |
|---|---|---|---|---|
| RTSP ingestion | FFmpeg / OpenCV | [ffmpeg.org/documentation.html](https://ffmpeg.org/documentation.html) · [OpenCV VideoCapture](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html) | [mpolinowski/opencv-rtsp](https://github.com/mpolinowski/opencv-rtsp) | — |
| File-watch ingestion | Python `watchdog` | [python-watchdog.readthedocs.io](https://python-watchdog.readthedocs.io/) | Docs' own quickstart | — |
| Queue | Redis Streams | [redis.io streams docs](https://redis.io/docs/latest/develop/data-types/streams/) | [Redis streaming use-cases](https://redis.io/docs/latest/develop/use-cases/streaming/) | — |
| Detection | YOLOv8 (Ultralytics) | [docs.ultralytics.com](https://docs.ultralytics.com/) | [Predict mode docs](https://docs.ultralytics.com/modes/predict/) | — |
| Tracking | ByteTrack / DeepSORT / Norfair | [Ultralytics track mode](https://docs.ultralytics.com/modes/track/) · [ByteTrack](https://github.com/ifzhang/ByteTrack) · [Deep SORT](https://github.com/nwojke/deep_sort) · [Norfair](https://github.com/tryolabs/norfair) | — | [SVSS13/Footfall-Counter](https://github.com/SVSS13/Footfall-Counter) · [Kerem-Kurt/YOLOv8-and-DEEPSORT-Human-Foot-Trafficker](https://github.com/Kerem-Kurt/YOLOv8-and-DEEPSORT-Human-Foot-Trafficker) |
| Demographics / attendance | DeepFace / InsightFace | [DeepFace](https://github.com/serengil/deepface) · [InsightFace](https://github.com/deepinsight/insightface) | README quickstart examples | — |
| Model serving | FastAPI + ONNX Runtime | [onnxruntime.ai/docs](https://onnxruntime.ai/docs/) · [pytorch.org/serve](https://pytorch.org/serve/) | [naxty/scikit-onnx-fastapi-example](https://github.com/naxty/scikit-onnx-fastapi-example) | same |
| Database | PostgreSQL / TimescaleDB | [postgresql.org/docs](https://www.postgresql.org/docs/) · [docs.timescale.com](https://docs.timescale.com/) | — | — |
| Backend API | FastAPI | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/) | [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/) | — |
| Dashboard | Grafana | [Grafana Postgres data source](https://grafana.com/docs/grafana/latest/datasources/postgres/) | [TimescaleDB Grafana tutorial](https://docs.timescale.com/tutorials/latest/grafana/) | — |
| Orchestration | Docker Compose | [docs.docker.com/compose](https://docs.docker.com/compose/gettingstarted/) | same | [docker/awesome-compose](https://github.com/docker/awesome-compose) |
| Reverse proxy | Nginx | [docs.nginx.com reverse proxy guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/) | same | — |
| Monitoring | Prometheus | [prometheus.io first steps](https://prometheus.io/docs/introduction/first_steps/) | same | — |
| Object storage (optional) | MinIO | [min.io/docs](https://min.io/docs/) | README quickstart | [github.com/minio/minio](https://github.com/minio/minio) |
