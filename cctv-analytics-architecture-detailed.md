# Retail CCTV Analytics — Detailed Architecture, Tech Stack & Implementation Plan
**Project:** Single-Store Pilot — People Detection, Demographics & Attendance
**Prepared as:** Technical Architecture Reference (v2 — expanded with tech stack, methods, and detailed timeline)

---

## 1. Project Scope (as finalized)

| Item | Decision |
|---|---|
| Deployment | Single store, on-premise only (no cloud) |
| Source | Existing DVR/NVR |
| Ingestion | Both RTSP (live) and file-based export supported |
| Processing | Local server (your ML model — treated as black box here) |
| Storage | Local server storage |
| Output | Web-based dashboard |
| Latency | Not critical — near-real-time / batch acceptable |

---

## 2. High-Level Architecture

```
[DVR/NVR] → [Ingestion Layer] → [Preprocessing] → [Queue] → [ML Inference] → [DB/Storage] → [API] → [Dashboard]
```

See `pipeline-diagram.mermaid` for the visual flow. Every arrow above is a service boundary with its own retry/error-handling logic — detailed per component below.

---

## 3. Component-Level Design & Tech Stack

### A. Ingestion Layer

| Aspect | Recommendation | Notes / Alternatives |
|---|---|---|
| RTSP client | **FFmpeg** (as a subprocess) or **OpenCV `VideoCapture`** with FFmpeg backend | GStreamer is more robust for hardware-accelerated decode but has a steeper ops learning curve — only worth it if the server has a capable GPU/VAAPI and camera count grows |
| File watcher | **Python `watchdog`** library, or native `inotify` on Linux | Watches a shared folder/FTP/SMB mount for new exported files; on FTP-only DVRs, an `lftp`/`rclone` cron mirror job feeds the watched folder |
| Language/runtime | Python 3.11+ | Keeps ingestion, preprocessing, and ML in one language ecosystem — fewer serialization boundaries |
| Resilience | Exponential-backoff reconnect on RTSP drop, per-camera health-check heartbeat written to Redis/DB | A stalled camera shouldn't block others — one ingestion process per camera, supervised by `systemd` or Docker's own restart policy |
| Packaging | One Docker container per camera stream, config-driven (camera list in a YAML/`.env` file) | Adding a camera = adding a config entry + restarting the ingestion compose service, not a code change |

### B. Preprocessing

| Aspect | Recommendation | Notes |
|---|---|---|
| Frame extraction | OpenCV frame grab at a fixed interval (2–5 fps target) | Confirmed adequate for demographics/attendance use cases; higher fps only helps tracking through fast-moving crowds |
| Adaptive sampling (optional, Phase 2 stretch) | Frame-differencing motion gate — skip ML inference entirely on frames with near-zero pixel delta from the previous kept frame | Meaningful compute savings during low-traffic hours; add only if Phase 3 shows the ML engine is the bottleneck |
| Dedup | Perceptual hashing (`pHash`) or simple Mean Squared Error/SSIM threshold between consecutive frames | Removes near-duplicate frames from a static scene before they hit the queue |
| Blank/dark filter | Mean pixel intensity + variance threshold | Cheap filter for night-mode/covered-lens frames that would otherwise waste ML cycles |
| Normalization | Resize/letterbox to the ML model's expected input shape at this stage, not inside the model service | Keeps the model service simple and makes the input contract easy to test independently |

### C. Queue/Buffer

| Option | Verdict for this pilot |
|---|---|
| **Redis Streams** | **Recommended.** Lightweight, single binary, built-in consumer groups, TTL/max-length trimming for backpressure — matches the "not latency-critical, single store" scale well |
| RabbitMQ | More durable delivery guarantees, but adds ops overhead (exchanges/queues/vhosts) that isn't justified at this scale |
| Kafka | Overkill — designed for much higher throughput/multi-consumer fan-out than one store needs; revisit only at multi-store rollout |

Backpressure policy: cap stream length (e.g., `MAXLEN ~ 5000`), drop-oldest on overflow, and log a warning metric so a chronically slow ML engine is visible rather than silently losing data.

### D. ML Inference Engine (your model — black box, contract-defined here)

**Input contract:** `{camera_id, timestamp, frame (JPEG bytes or path)}`
**Output contract:** `{camera_id, timestamp, detections: [{bbox, track_id, age_range, gender, confidence, attendance_match: employee_id | null}]}`

The model itself stays a black box, but for context, the pipeline is designed to comfortably fit any implementation built on these common methods:

- **Person detection:** YOLOv8/YOLOv9 (or a lighter YOLO variant if the server is CPU-only)
- **Multi-object tracking** (to avoid double-counting the same person across frames): ByteTrack, DeepSORT, or Norfair — this is what turns raw per-frame detections into a "unique visitor" count
- **Demographic estimation:** pretrained age/gender models (e.g., InsightFace-based or DeepFace-wrapped) — flagged in Section 8 as an accuracy-sensitive component worth validating on your own footage before trusting reported numbers
- **Attendance matching:** either face-embedding similarity search (ArcFace/FaceNet + a vector index) for identity-based attendance, or zone/dwell-time rules (a defined bounding region + minimum time-in-zone) for a coarser, privacy-lighter approach — see the open question in Section 5

**Serving the model:** wrap it behind a small **FastAPI** or **Flask** microservice (ONNXRuntime or TorchServe underneath, depending on how the model is exported) so the rest of the pipeline talks to a stable HTTP/gRPC contract regardless of what changes inside the model.

**Compute:** at 2–5 fps across a handful of cameras, a single modest GPU (e.g., RTX 3060/4060-class, or a T4-equivalent workstation card) comfortably keeps up. Pure CPU inference is workable only for 1–2 cameras at the low end of the fps range — worth a quick benchmark in Phase 3 before committing to CPU-only hardware.

### E. Local Database

| Option | Verdict |
|---|---|
| **PostgreSQL** | **Recommended**, even at pilot scale — footfall/demographic queries are naturally time-series-ish and benefit from real indexing and concurrent writes from the API + write-service |
| + TimescaleDB extension (optional) | Worth adding if footfall queries over long date ranges get slow; a drop-in Postgres extension, not a migration |
| SQLite | Acceptable only if this is a throwaway proof-of-concept with a single writer and no concurrent dashboard users |

**Indicative schema:**

```sql
cameras          (camera_id PK, store_id, name, rtsp_url, active)
events           (event_id PK, camera_id FK, track_id, ts, bbox_json)
demographics     (event_id FK, age_range, gender, confidence)
attendance_events(event_id FK, employee_id NULLABLE, match_confidence, method)  -- method: 'face' | 'zone'
employees        (employee_id PK, name, enrolled_face_embedding NULLABLE)      -- only if face-based attendance is chosen
snapshots        (event_id FK, file_path, taken_at)
```

`store_id` is included on `cameras` from day one per the multi-store note in Section 10, even though there's only one store now.

### F. Local Storage (snapshots/clips, optional)

- Flat directory structure on local disk: `/data/snapshots/{camera_id}/{yyyy-mm-dd}/{event_id}.jpg`
- Retention enforced by a nightly cron/`systemd timer` job (default: delete after 30 days, configurable)
- **Optional upgrade:** MinIO (S3-compatible, self-hosted) instead of raw disk paths — no benefit for a single store today, but makes a future multi-store sync job trivial since it's already speaking an S3 API. Flagged as optional, not required for pilot.

### G. Backend API

- **FastAPI** (Python) — recommended over Node/Express mainly because it keeps the whole stack in one language alongside the ingestion/ML services, and its async support pairs naturally with a queue-based pipeline
- REST endpoints for the dashboard; polling every 10–30s is sufficient given latency isn't critical (avoids the added complexity of WebSockets/SSE for a pilot)
- Auth: simple session or JWT login, single role type (store ops/manager) — no need for a permissions system yet

### H. Web Dashboard

Two viable paths, worth deciding explicitly rather than defaulting:

1. **Grafana pointed directly at PostgreSQL** — for a pilot, this can save the bulk of Phase 6's time. Footfall trends, demographic breakdowns, and time-series charts are exactly what Grafana is built for, and it ships with alerting for free (e.g., "camera offline > 10 min").
2. **Custom React dashboard** (Recharts/Chart.js for charts) — needed only if there's an interactive requirement Grafana can't cover, such as manually correcting an attendance match or an employee-enrollment UI.

**Recommended hybrid:** Grafana for analytics/trend views, a very small custom page (or a couple of API-backed forms) for the handful of admin actions Grafana doesn't do. This is called out explicitly because it changes the Phase 6 estimate — see Section 7.

### I. Deployment / Infrastructure

| Aspect | Recommendation |
|---|---|
| Orchestration | Docker Compose (one file, one server) — Kubernetes would be pure overhead at this scale |
| OS | Ubuntu Server LTS |
| Reverse proxy | Nginx — TLS termination even on LAN, plus basic auth in front of Grafana/API if not already handled at the app layer |
| Monitoring | Prometheus + Grafana (reuse the same Grafana instance as the dashboard) for service health/queue depth/camera uptime; otherwise plain structured logging (Python `logging` + rotating file handler) is enough at pilot scale |
| Backup | Nightly `rsync`/`restic` to a local NAS or external drive — see the no-cloud data-loss risk noted in Section 8 |

---

## 4. Data Flow (Step-by-Step)

1. Camera records → DVR/NVR stores footage
2. Ingestion layer pulls either live RTSP stream or picks up exported files; reconnects with backoff on failure
3. Frames extracted at fixed intervals, filtered (blank/dark) and deduplicated
4. Frames pushed to Redis Streams queue (bounded, drop-oldest on overflow)
5. ML engine consumes queue, runs detection + tracking + demographics + attendance logic, returns structured JSON per the contract in Section 3D
6. Results written to PostgreSQL (+ optional snapshot to local disk/MinIO)
7. FastAPI backend reads DB, exposes REST endpoints (live stats, historical reports, attendance logs)
8. Dashboard (Grafana + optional custom app) polls/queries the API/DB and renders charts/tables

---

## 5. Open Questions / Decisions Needed Before Build

These affect estimates in Section 7 and should be confirmed early:

- **Attendance method:** face-recognition-based (needs employee enrollment flow + biometric data handling/consent considerations) vs. zone/dwell-time-based (simpler, no biometric storage, coarser accuracy)? This is the single biggest swing factor in Phase 3 scope.
- **Camera count for the pilot:** the plan below assumes "a few," not dozens — confirm before Phase 1 sizing
- **Dashboard approach:** Grafana-first hybrid (faster) vs. fully custom React dashboard (slower, more flexible) — see Section 3H
- **GPU availability:** is a GPU-equipped server already available, or does procurement need to happen before Phase 3?

---

## 6. Phase-Wise Plan with Detailed Timelines

*(Estimates assume a single developer or small team, pilot scale, and that your ML model already exists — model development time itself is excluded)*

| Phase | Work | Sub-tasks | Estimated Time |
|---|---|---|---|
| **Phase 1: Setup & Ingestion** | Local server setup, DVR/NVR connectivity | Provision server + OS; confirm DVR/NVR RTSP URLs/credentials per channel; build RTSP puller with reconnect logic; build file-watcher fallback for export-only channels; validate 24h+ stream stability | 1 – 1.5 weeks |
| **Phase 2: Preprocessing Pipeline** | Frame extraction, filtering, queueing | Frame extraction service at configurable fps; blank/dark filter; dedup (pHash/SSIM); stand up Redis Streams; wire ingestion → queue | 3 – 5 days |
| **Phase 3: ML Integration** | Wire existing model into the pipeline | Finalize input/output contract (Section 3D); build model-serving wrapper (FastAPI/Flask + ONNXRuntime or TorchServe); GPU vs CPU benchmark; test against recorded footage; validate demographic accuracy on real store footage; implement chosen attendance method (face enrollment flow **or** zone-rule config) | 1 – 2 weeks (face-recognition path trends toward the higher end; zone-based trends toward the lower end) |
| **Phase 4: Database & Storage** | Schema, write-service, retention | Finalize Postgres schema (Section 3E); write-service consuming ML output → DB; snapshot storage + retention cron; local backup job (rsync/restic to NAS) | 3 – 5 days |
| **Phase 5: Backend API** | REST endpoints for dashboard | Live stats endpoint; historical/footfall trend endpoint; attendance log endpoint; auth (session/JWT); basic rate-limiting/error handling | 4 – 6 days |
| **Phase 6: Dashboard (Web)** | Visualization layer | **If Grafana-first hybrid:** Postgres data-source wiring + panel/dashboard building + basic alerting (3–5 days); **plus** small custom app for admin actions if needed (2–4 days). **If fully custom React:** charts + tables + auth UI (1 – 1.5 weeks) | 3 days – 1.5 weeks depending on path chosen (Section 3H) |
| **Phase 7: Integration Testing & Tuning** | End-to-end validation | Real store footage end-to-end run; fix queue/latency bottlenecks; tune fps vs. accuracy vs. compute load; verify reconnect/failure handling on ingestion; load-test with all cameras live simultaneously | 1 week |
| **Phase 8: Pilot Deployment** | Go-live at store | Deploy on-site; monitor stability (queue depth, camera uptime, disk usage); gather store-manager feedback on dashboard usability; triage and patch issues | 1 week (monitoring period, ongoing) |

**Total estimated time: ~6 – 8.5 weeks** for a working single-store pilot, excluding ML model development itself. The wider range vs. the original estimate reflects the two swing factors called out in Section 5 (attendance method, dashboard approach) — pinning those down early tightens this considerably.

---

## 7. Tech Stack Summary Table

| Layer | Technology | Why |
|---|---|---|
| Ingestion | Python, FFmpeg/OpenCV, `watchdog` | DVR/NVR-agnostic, one language across ingestion/preprocessing/ML |
| Queue | Redis Streams | Lightweight, single binary, sufficient throughput, easy backpressure control |
| Model serving | FastAPI/Flask + ONNXRuntime or TorchServe | Stable HTTP contract around a black-box model that may itself evolve |
| Compute | 1x mid-range GPU (RTX 3060/4060-class or equivalent) | Keeps up with 2–5 fps across a handful of cameras; CPU-only viable only at low camera counts |
| Database | PostgreSQL (+ optional TimescaleDB) | Concurrent writes, real indexing, time-series-friendly queries |
| Object storage | Local disk (optionally MinIO) | Snapshot/clip retention; MinIO only pays off if multi-store sync is on the near-term roadmap |
| Backend API | FastAPI | Async-friendly, same language as the rest of the stack |
| Dashboard | Grafana (+ small custom app as needed) | Fastest path to a usable pilot dashboard; custom React only where Grafana can't reach |
| Orchestration | Docker Compose | Right-sized for one server, one store |
| Reverse proxy | Nginx | TLS + basic auth in front of everything |
| Monitoring | Prometheus + Grafana | Reuses the dashboard stack for service/camera health |
| Backup | rsync/restic → local NAS or external drive | Mitigates the no-cloud data-loss risk (Section 8) |

---

## 8. Key Assumptions & Risks

| Assumption / Risk | Mitigation |
|---|---|
| DVR/NVR supports RTSP; file-export is fallback | File-watcher path built in from Phase 1, not bolted on later |
| Single camera or a few cameras per store, not dozens | Re-scope ingestion/compute sizing if camera count is actually 20+ |
| No cloud = no external backup; local disk failure = data loss | Nightly local backup job to NAS/external drive (Section 3I) |
| Attendance logic (face-recognition vs. zone-based) is undecided | Flagged in Section 5 as a pre-build decision — materially changes Phase 3 scope and raises data-handling/consent considerations if face-based |
| Demographic model accuracy on your specific store's camera angles/lighting is unvalidated | Budget time in Phase 3 to validate against real footage before trusting reported numbers operationally |
| Dashboard is internal-use only (store manager/ops) | No heavy auth/multi-tenant system needed at pilot stage; revisit if customer-facing use is ever considered |

---

## 9. What Changes for Multi-Store (future, not now)

Just so it's noted for later — when you scale beyond one store, you'd add:
- Central server aggregating from multiple local/edge boxes, OR edge processing per store + syncing summarized data centrally
- Store-level identifiers in DB schema (already included now — see `store_id` in Section 3E)
- Load balancing on ingestion if pulling many RTSP streams at once
- MinIO (or equivalent) becomes worth adopting immediately, since it turns the "sync summarized data centrally" step into an S3-to-S3 job instead of a bespoke file-transfer script

Not needed now, just keep the DB schema store-ID-ready so it's an easy extension later — already reflected in the schema above.
