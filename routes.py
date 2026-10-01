"""REST routes for the VS corp CCTV retail analytics panel (all under /api)."""

import csv
import io
import os
import shutil
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from database import get_db

router = APIRouter(prefix="/api")
RECORDINGS_DIR = Path(__file__).resolve().parent / "runtime" / "recordings"
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
BITRATE_LIMIT_KBPS = float(os.environ.get("BITRATE_LIMIT_KBPS", 1000))
EVENT_TYPES_HINT = "e.g. Person Recognition, Cash Drawer Sequence, Intrusion Detection, Customer Unattended"

Db = sqlite3.Connection


# ---------- helpers ----------
def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def one(db: Db, sql, args=()):
    row = db.execute(sql, args).fetchone()
    return dict(row) if row else None


def must(db: Db, table, row_id, label):
    row = one(db, f"SELECT * FROM {table} WHERE id = ?", (row_id,))
    if not row:
        raise HTTPException(404, f"{label} not found")
    return row


def pct_change(current, previous):
    return None if not previous else round((current - previous) / previous * 100, 2)


def parse_day(value: Optional[str], default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, f"Invalid date '{value}', use YYYY-MM-DD")


def page_args(page, per_page):
    return per_page, (page - 1) * per_page


def update_fields(db: Db, table, row_id, data: dict, extra=None):
    data = {k: v for k, v in data.items() if v is not None}
    if extra:
        data.update(extra)
    if not data:
        return
    sets = ", ".join(f"{k} = ?" for k in data)
    db.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*data.values(), row_id))


def insert(db: Db, table, data: dict):
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    return db.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(data.values())).lastrowid


# ---------- locations ----------
class LocationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/locations")
def list_locations(db: Db = Depends(get_db)):
    return {"locations": rows(db.execute("""
        SELECT l.id, l.name, COUNT(c.id) AS camera_count,
               COALESCE(SUM(c.status = 'online'), 0) AS online_count
        FROM locations l LEFT JOIN cameras c ON c.location_id = l.id
        GROUP BY l.id ORDER BY l.name"""))}


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, db: Db = Depends(get_db)):
    try:
        new_id = insert(db, "locations", {"name": body.name.strip()})
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Location already exists")
    return must(db, "locations", new_id, "Location")


@router.put("/locations/{location_id}")
def rename_location(location_id: int, body: LocationIn, db: Db = Depends(get_db)):
    must(db, "locations", location_id, "Location")
    try:
        db.execute("UPDATE locations SET name = ? WHERE id = ?", (body.name.strip(), location_id))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Location already exists")
    return must(db, "locations", location_id, "Location")


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(location_id: int, db: Db = Depends(get_db)):
    must(db, "locations", location_id, "Location")
    db.execute("DELETE FROM locations WHERE id = ?", (location_id,))


# ---------- cameras ----------
class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    location_id: int
    source_type: str = "RTSP"
    rtsp_url: Optional[str] = None


class CameraPatch(BaseModel):
    name: Optional[str] = None
    location_id: Optional[int] = None
    source_type: Optional[str] = None
    rtsp_url: Optional[str] = None


class Heartbeat(BaseModel):
    status: str = Field(pattern="^(online|offline)$")
    codec: Optional[str] = None
    bitrate_kbps: Optional[float] = None
    resolution: Optional[str] = None


CAMERA_SELECT = """
    SELECT c.id, c.name, c.location_id, l.name AS location, c.source_type, c.rtsp_url, c.status,
           c.codec, c.bitrate_kbps, c.resolution, c.last_seen,
           CASE WHEN c.bitrate_kbps > ? THEN 1 ELSE 0 END AS bitrate_violation
    FROM cameras c JOIN locations l ON l.id = c.location_id"""


@router.get("/cameras")
def list_cameras(location_id: Optional[int] = None, status: Optional[str] = Query(None, pattern="^(online|offline)$"),
                 source_type: Optional[str] = None, name: Optional[str] = None, db: Db = Depends(get_db)):
    where, args = [], [BITRATE_LIMIT_KBPS]
    if location_id:
        where.append("c.location_id = ?"); args.append(location_id)
    if status:
        where.append("c.status = ?"); args.append(status)
    if source_type:
        where.append("c.source_type = ?"); args.append(source_type)
    if name:
        where.append("c.name LIKE ?"); args.append(f"%{name}%")
    sql = CAMERA_SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY l.name, c.name"
    cams = rows(db.execute(sql, args))
    totals = one(db, "SELECT COUNT(*) AS total, COALESCE(SUM(status='online'),0) AS online, "
                     "COALESCE(SUM(bitrate_kbps > ?),0) AS bitrate_violations FROM cameras", (BITRATE_LIMIT_KBPS,))
    return {"cameras": cams, "totals": {**totals, "offline": totals["total"] - totals["online"]},
            "bitrate_limit_kbps": BITRATE_LIMIT_KBPS, "last_updated": now_iso()}


@router.post("/cameras", status_code=201)
def create_camera(body: CameraIn, db: Db = Depends(get_db)):
    must(db, "locations", body.location_id, "Location")
    new_id = insert(db, "cameras", {**body.model_dump(), "created_at": now_iso()})
    return one(db, CAMERA_SELECT + " WHERE c.id = ?", (BITRATE_LIMIT_KBPS, new_id))


@router.get("/cameras/summary")
def camera_summary(db: Db = Depends(get_db)):
    """Data for the Camera Statistics screen."""
    total = one(db, "SELECT COUNT(*) AS n, COALESCE(SUM(status='online'),0) AS online, "
                    "COALESCE(SUM(bitrate_kbps > ?),0) AS violations FROM cameras", (BITRATE_LIMIT_KBPS,))
    by_type = rows(db.execute("SELECT source_type, COUNT(*) AS total, COALESCE(SUM(status='online'),0) AS active "
                              "FROM cameras GROUP BY source_type"))
    by_location = rows(db.execute("""
        SELECT l.id, l.name, COUNT(c.id) AS total, COALESCE(SUM(c.status='online'),0) AS active,
               COALESCE(SUM(c.status!='online'),0) AS disconnected,
               COALESCE(SUM(c.bitrate_kbps > ?),0) AS bitrate_violations
        FROM locations l LEFT JOIN cameras c ON c.location_id = l.id GROUP BY l.id ORDER BY l.name""", (BITRATE_LIMIT_KBPS,)))
    disconnected = [loc for loc in by_location if loc["total"] and not loc["active"]]
    return {
        "cameras": {"total": total["n"], "active": total["online"], "bitrate_violations": total["violations"]},
        "locations": {"total": len(by_location), "active": sum(1 for loc in by_location if loc["active"])},
        "by_source_type": by_type, "by_location": by_location, "disconnected_locations": disconnected,
        "bitrate_limit_kbps": BITRATE_LIMIT_KBPS, "last_updated": now_iso(),
    }


@router.get("/cameras/{camera_id}")
def get_camera(camera_id: int, db: Db = Depends(get_db)):
    cam = one(db, CAMERA_SELECT + " WHERE c.id = ?", (BITRATE_LIMIT_KBPS, camera_id))
    if not cam:
        raise HTTPException(404, "Camera not found")
    return cam


@router.patch("/cameras/{camera_id}")
def update_camera(camera_id: int, body: CameraPatch, db: Db = Depends(get_db)):
    must(db, "cameras", camera_id, "Camera")
    if body.location_id:
        must(db, "locations", body.location_id, "Location")
    update_fields(db, "cameras", camera_id, body.model_dump())
    return get_camera(camera_id, db)


@router.post("/cameras/{camera_id}/heartbeat")
def camera_heartbeat(camera_id: int, body: Heartbeat, db: Db = Depends(get_db)):
    """Called by the stream monitor to report live health."""
    must(db, "cameras", camera_id, "Camera")
    update_fields(db, "cameras", camera_id, body.model_dump(), {"last_seen": now_iso()})
    return get_camera(camera_id, db)


@router.delete("/cameras/{camera_id}", status_code=204)
def delete_camera(camera_id: int, db: Db = Depends(get_db)):
    must(db, "cameras", camera_id, "Camera")
    db.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))


@router.get("/cameras/{camera_id}/snapshot")
def camera_snapshot(camera_id: int, db: Db = Depends(get_db)):
    """Grab one JPEG frame from the camera's RTSP stream (404 when unreachable)."""
    cam = must(db, "cameras", camera_id, "Camera")
    if not cam["rtsp_url"] or cam["status"] != "online":
        raise HTTPException(404, "No live stream available")
    import cv2
    cap = cv2.VideoCapture(cam["rtsp_url"])
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok:
        raise HTTPException(404, "Could not read a frame from the stream")
    ok, buf = cv2.imencode(".jpg", frame)
    return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# ---------- DVR recordings ----------
@router.get("/recordings")
def list_recordings(day: Optional[str] = Query(None, alias="date"), location_id: Optional[int] = None,
                    name: Optional[str] = None, page: int = Query(1, ge=1), per_page: int = Query(10, ge=1, le=100),
                    db: Db = Depends(get_db)):
    """One row per camera with 24 hour slots; a slot carries a recording id when footage exists."""
    the_day = parse_day(day, date.today())
    where, args = [], []
    if location_id:
        where.append("c.location_id = ?"); args.append(location_id)
    if name:
        where.append("c.name LIKE ?"); args.append(f"%{name}%")
    clause = " WHERE " + " AND ".join(where) if where else ""
    total = one(db, f"SELECT COUNT(*) AS n FROM cameras c{clause}", args)["n"]
    limit, offset = page_args(page, per_page)
    cams = rows(db.execute(f"""SELECT c.id, c.name, c.source_type, l.name AS location FROM cameras c
                               JOIN locations l ON l.id = c.location_id{clause}
                               ORDER BY l.name, c.name LIMIT ? OFFSET ?""", (*args, limit, offset)))
    result = []
    for cam in cams:
        slots = {h: None for h in range(24)}
        recs = rows(db.execute("""SELECT id, start_ts, end_ts FROM recordings WHERE camera_id = ?
                                  AND date(start_ts) <= ? AND date(COALESCE(end_ts, start_ts)) >= ?""",
                               (cam["id"], the_day.isoformat(), the_day.isoformat())))
        for rec in recs:
            start = datetime.fromisoformat(rec["start_ts"])
            end = datetime.fromisoformat(rec["end_ts"]) if rec["end_ts"] else start
            first = start.hour if start.date() == the_day else 0
            last = end.hour if end.date() == the_day else 23
            for hour in range(first, last + 1):
                slots[hour] = rec["id"]
        cam["slots"] = [{"hour": h, "label": f"{h:02d}:00 - {h + 1:02d}:00", "recording_id": slots[h]} for h in range(24)]
        result.append(cam)
    return {"date": the_day.isoformat(), "timezone": "Asia/Kolkata", "total": total, "page": page,
            "pages": max(1, -(-total // per_page)), "feeds": result}


@router.post("/recordings", status_code=201)
async def upload_recording(camera_id: int = Form(...), start_ts: str = Form(...), end_ts: Optional[str] = Form(None),
                           file: UploadFile = File(...), db: Db = Depends(get_db)):
    must(db, "cameras", camera_id, "Camera")
    try:
        datetime.fromisoformat(start_ts)
        if end_ts:
            datetime.fromisoformat(end_ts)
    except ValueError:
        raise HTTPException(400, "start_ts/end_ts must be ISO datetimes")
    target = RECORDINGS_DIR / f"{uuid.uuid4().hex}{Path(file.filename or 'clip.mp4').suffix.lower() or '.mp4'}"
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)
    new_id = insert(db, "recordings", {"camera_id": camera_id, "start_ts": start_ts, "end_ts": end_ts, "file_path": str(target)})
    return {"id": new_id, "camera_id": camera_id, "start_ts": start_ts, "end_ts": end_ts}


@router.get("/recordings/{recording_id}/video")
def recording_video(recording_id: int, db: Db = Depends(get_db)):
    rec = must(db, "recordings", recording_id, "Recording")
    path = Path(rec["file_path"])
    if not path.is_file():
        raise HTTPException(404, "Recording file is missing on disk")
    return FileResponse(path)


# ---------- events (audit report + graphical insights) ----------
class EventIn(BaseModel):
    event_type: str = Field(min_length=1, description=EVENT_TYPES_HINT)
    camera_id: Optional[int] = None
    location_id: Optional[int] = None
    ts: Optional[str] = None
    result: Optional[str] = None
    image_url: Optional[str] = None
    recording_id: Optional[int] = None
    important: bool = False


EVENT_SELECT = """
    SELECT e.id, e.event_type, e.ts, e.result, e.image_url, e.recording_id, e.important, e.ticket_id,
           e.camera_id, c.name AS camera, COALESCE(e.location_id, c.location_id) AS location_id, l.name AS location
    FROM events e LEFT JOIN cameras c ON c.id = e.camera_id
    LEFT JOIN locations l ON l.id = COALESCE(e.location_id, c.location_id)"""


def event_filters(start, end, location_id, camera_id, event_type, important, q):
    where, args = [], []
    if start:
        where.append("e.ts >= ?"); args.append(start)
    if end:
        where.append("e.ts <= ?"); args.append(end)
    if location_id:
        where.append("COALESCE(e.location_id, c.location_id) = ?"); args.append(location_id)
    if camera_id:
        where.append("e.camera_id = ?"); args.append(camera_id)
    if event_type:
        where.append("e.event_type = ?"); args.append(event_type)
    if important is not None:
        where.append("e.important = ?"); args.append(int(important))
    if q:
        where.append("e.result LIKE ?"); args.append(f"%{q}%")
    return (" WHERE " + " AND ".join(where)) if where else "", args


@router.get("/events")
def list_events(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None,
                camera_id: Optional[int] = None, event_type: Optional[str] = None, important: Optional[bool] = None,
                q: Optional[str] = None, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=200),
                db: Db = Depends(get_db)):
    """`start`/`end` are ISO datetimes (e.g. 2026-07-18T00:00:00)."""
    clause, args = event_filters(start, end, location_id, camera_id, event_type, important, q)
    total = one(db, f"SELECT COUNT(*) AS n FROM events e LEFT JOIN cameras c ON c.id = e.camera_id{clause}", args)["n"]
    limit, offset = page_args(page, per_page)
    items = rows(db.execute(f"{EVENT_SELECT}{clause} ORDER BY e.ts DESC LIMIT ? OFFSET ?", (*args, limit, offset)))
    return {"total": total, "page": page, "per_page": per_page, "pages": max(1, -(-total // per_page)), "items": items}


@router.get("/events/types")
def event_types(db: Db = Depends(get_db)):
    return {"event_types": [r["event_type"] for r in db.execute("SELECT DISTINCT event_type FROM events ORDER BY 1")]}


@router.get("/events/export")
def export_events(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None,
                  camera_id: Optional[int] = None, event_type: Optional[str] = None,
                  important: Optional[bool] = None, q: Optional[str] = None, db: Db = Depends(get_db)):
    clause, args = event_filters(start, end, location_id, camera_id, event_type, important, q)
    data = rows(db.execute(f"{EVENT_SELECT}{clause} ORDER BY e.ts DESC", args))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "timestamp", "location", "camera", "event_type", "result", "important", "ticket_id"])
    for r in data:
        writer.writerow([r["id"], r["ts"], r["location"], r["camera"], r["event_type"], r["result"], r["important"], r["ticket_id"]])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit-report.csv"})


@router.post("/events", status_code=201)
def create_event(body: EventIn, db: Db = Depends(get_db)):
    if body.camera_id:
        must(db, "cameras", body.camera_id, "Camera")
    data = body.model_dump()
    data["ts"] = data["ts"] or now_iso()
    data["important"] = int(data["important"])
    new_id = insert(db, "events", data)
    return one(db, f"{EVENT_SELECT} WHERE e.id = ?", (new_id,))


@router.get("/events/summary")
def events_summary(location_id: Optional[int] = None, db: Db = Depends(get_db)):
    """Week / yesterday / today violation totals with per-type counts and change vs the previous period."""
    today = date.today()

    def period(first: date, last: date):
        args = [first.isoformat(), last.isoformat()]
        loc = ""
        if location_id:
            loc = " AND COALESCE(e.location_id, c.location_id) = ?"
            args.append(location_id)
        data = rows(db.execute(f"""SELECT e.event_type, COUNT(*) AS n FROM events e LEFT JOIN cameras c ON c.id = e.camera_id
                                   WHERE date(e.ts) BETWEEN ? AND ?{loc} GROUP BY e.event_type ORDER BY n DESC""", args))
        return {"total": sum(r["n"] for r in data), "by_type": {r["event_type"]: r["n"] for r in data},
                "from": first.isoformat(), "to": last.isoformat()}

    def build(first, last, prev_first, prev_last):
        cur, prev = period(first, last), period(prev_first, prev_last)
        return {**cur, "change_pct": pct_change(cur["total"], prev["total"]),
                "previous": {"from": prev["from"], "to": prev["to"], "total": prev["total"]}}

    d = timedelta(days=1)
    return {
        "week": build(today - 7 * d, today - d, today - 14 * d, today - 8 * d),
        "yesterday": build(today - d, today - d, today - 2 * d, today - 2 * d),
        "today": build(today, today, today - d, today - d),
    }


@router.get("/events/stats")
def events_stats(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None,
                 db: Db = Depends(get_db)):
    """Counts per event type and per day for the statistics charts."""
    today = date.today()
    first = parse_day(start, today - timedelta(days=15)).isoformat()
    last = parse_day(end, today).isoformat()
    args = [first, last]
    loc = ""
    if location_id:
        loc = " AND COALESCE(e.location_id, c.location_id) = ?"
        args.append(location_id)
    base = f"FROM events e LEFT JOIN cameras c ON c.id = e.camera_id WHERE date(e.ts) BETWEEN ? AND ?{loc}"
    return {"start": first, "end": last,
            "by_type": rows(db.execute(f"SELECT e.event_type, COUNT(*) AS count {base} GROUP BY e.event_type ORDER BY count DESC", args)),
            "by_day": rows(db.execute(f"SELECT date(e.ts) AS day, COUNT(*) AS count {base} GROUP BY day ORDER BY day", args))}


@router.patch("/events/{event_id}")
def patch_event(event_id: int, important: Optional[bool] = None, ticket_id: Optional[int] = None, db: Db = Depends(get_db)):
    must(db, "events", event_id, "Event")
    update_fields(db, "events", event_id, {"important": None if important is None else int(important), "ticket_id": ticket_id})
    return one(db, f"{EVENT_SELECT} WHERE e.id = ?", (event_id,))


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, db: Db = Depends(get_db)):
    must(db, "events", event_id, "Event")
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))


# ---------- employees + FR attendance ----------
class EmployeeIn(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    location_id: Optional[int] = None


class ClockIn(BaseModel):
    employee_code: str
    kind: str = Field(pattern="^(in|out)$")
    ts: Optional[str] = None
    location_id: Optional[int] = None


@router.get("/employees")
def list_employees(q: Optional[str] = None, location_id: Optional[int] = None, db: Db = Depends(get_db)):
    where, args = [], []
    if q:
        where.append("(e.name LIKE ? OR e.code LIKE ?)"); args += [f"%{q}%"] * 2
    if location_id:
        where.append("e.location_id = ?"); args.append(location_id)
    clause = " WHERE " + " AND ".join(where) if where else ""
    return {"employees": rows(db.execute(f"""SELECT e.id, e.code, e.name, e.location_id, l.name AS location FROM employees e
                                             LEFT JOIN locations l ON l.id = e.location_id{clause} ORDER BY e.name""", args))}


@router.post("/employees", status_code=201)
def create_employee(body: EmployeeIn, db: Db = Depends(get_db)):
    try:
        new_id = insert(db, "employees", body.model_dump())
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Employee code already exists")
    return must(db, "employees", new_id, "Employee")


@router.delete("/employees/{employee_id}", status_code=204)
def delete_employee(employee_id: int, db: Db = Depends(get_db)):
    must(db, "employees", employee_id, "Employee")
    db.execute("DELETE FROM employees WHERE id = ?", (employee_id,))


@router.post("/attendance/clock", status_code=201)
def clock(body: ClockIn, db: Db = Depends(get_db)):
    """Record a clock-in/out (called by face-recognition or manually)."""
    emp = one(db, "SELECT * FROM employees WHERE code = ?", (body.employee_code,))
    if not emp:
        raise HTTPException(404, "Employee not found")
    ts = body.ts or now_iso()
    insert(db, "attendance_logs", {"employee_id": emp["id"], "ts": ts, "kind": body.kind, "location_id": body.location_id or emp["location_id"]})
    return {"employee": emp["name"], "kind": body.kind, "ts": ts}


def hours_between(start, end):
    if not start or not end:
        return None
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600, 2)


@router.get("/attendance")
def attendance(day: Optional[str] = Query(None, alias="date"), status: Optional[str] = Query(None, pattern="^(present|absent)$"),
               location_id: Optional[int] = None, q: Optional[str] = None, standard_hours: float = 8, db: Db = Depends(get_db)):
    the_day = parse_day(day, date.today()).isoformat()
    where, args = [], []
    if location_id:
        where.append("e.location_id = ?"); args.append(location_id)
    if q:
        where.append("e.name LIKE ?"); args.append(f"%{q}%")
    clause = " WHERE " + " AND ".join(where) if where else ""
    emps = rows(db.execute(f"SELECT e.id, e.code, e.name FROM employees e{clause} ORDER BY e.name", args))
    out, present = [], 0
    for emp in emps:
        logs = rows(db.execute("""SELECT a.ts, a.kind, l.name AS location FROM attendance_logs a LEFT JOIN locations l ON l.id = a.location_id
                                  WHERE a.employee_id = ? AND date(a.ts) = ? ORDER BY a.ts""", (emp["id"], the_day)))
        ins, outs = [x for x in logs if x["kind"] == "in"], [x for x in logs if x["kind"] == "out"]
        first_in = ins[0] if ins else (logs[0] if logs else None)
        last_out = outs[-1] if outs else None
        total = hours_between(first_in["ts"], last_out["ts"]) if first_in and last_out else None
        is_present = first_in is not None
        present += is_present
        out.append({**emp, "present": is_present, "clock_in": first_in and first_in["ts"], "clock_in_location": first_in and first_in["location"],
                    "clock_out": last_out and last_out["ts"], "clock_out_location": last_out and last_out["location"],
                    "total_hours": total, "overtime_hours": None if total is None else max(0, round(total - standard_hours, 2)),
                    "log_count": len(logs)})
    if status:
        out = [r for r in out if r["present"] == (status == "present")]
    return {"date": the_day, "summary": {"present": present, "absent": len(emps) - present, "total": len(emps)}, "employees": out}


@router.get("/attendance/{employee_id}/logs")
def attendance_logs(employee_id: int, start: Optional[str] = None, end: Optional[str] = None, db: Db = Depends(get_db)):
    emp = must(db, "employees", employee_id, "Employee")
    today = date.today()
    first = parse_day(start, today).isoformat()
    last = parse_day(end, today).isoformat()
    logs = rows(db.execute("""SELECT a.ts, a.kind, l.name AS location FROM attendance_logs a LEFT JOIN locations l ON l.id = a.location_id
                              WHERE a.employee_id = ? AND date(a.ts) BETWEEN ? AND ? ORDER BY a.ts""", (employee_id, first, last)))
    return {"employee": emp, "logs": logs}


@router.get("/attendance/report")
def attendance_report(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None, db: Db = Depends(get_db)):
    """Present-employee count per day (Reports Panel)."""
    today = date.today()
    first = parse_day(start, today - timedelta(days=29)).isoformat()
    last = parse_day(end, today).isoformat()
    args = [first, last]
    loc = ""
    if location_id:
        loc = " AND e.location_id = ?"
        args.append(location_id)
    total = one(db, "SELECT COUNT(*) AS n FROM employees e WHERE 1=1" + (" AND e.location_id = ?" if location_id else ""),
                (location_id,) if location_id else ())["n"]
    days = rows(db.execute(f"""SELECT date(a.ts) AS day, COUNT(DISTINCT a.employee_id) AS present FROM attendance_logs a
                               JOIN employees e ON e.id = a.employee_id WHERE date(a.ts) BETWEEN ? AND ?{loc} GROUP BY day ORDER BY day""", args))
    return {"total_employees": total, "days": [{**d, "absent": total - d["present"]} for d in days]}


# ---------- tickets ----------
class TicketIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    priority: str = Field("medium", pattern="^(low|medium|high|critical)$")
    location_id: Optional[int] = None
    event_id: Optional[int] = None


class TicketPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(open|in_progress|closed)$")
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    location_id: Optional[int] = None
    starred: Optional[bool] = None


TICKET_SELECT = "SELECT t.*, l.name AS location FROM tickets t LEFT JOIN locations l ON l.id = t.location_id"


@router.get("/tickets")
def list_tickets(q: Optional[str] = None, location_id: Optional[int] = None, status: Optional[str] = None,
                 priority: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
                 starred: Optional[bool] = None, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=200),
                 db: Db = Depends(get_db)):
    where, args = [], []
    if q:
        where.append("(CAST(t.id AS TEXT) = ? OR t.title LIKE ?)"); args += [q.lstrip("#"), f"%{q}%"]
    if location_id:
        where.append("t.location_id = ?"); args.append(location_id)
    if status:
        where.append("t.status = ?"); args.append(status)
    if priority:
        where.append("t.priority = ?"); args.append(priority)
    if start:
        where.append("date(t.created_at) >= ?"); args.append(start)
    if end:
        where.append("date(t.created_at) <= ?"); args.append(end)
    if starred is not None:
        where.append("t.starred = ?"); args.append(int(starred))
    clause = " WHERE " + " AND ".join(where) if where else ""
    total = one(db, f"SELECT COUNT(*) AS n FROM tickets t{clause}", args)["n"]
    limit, offset = page_args(page, per_page)
    items = rows(db.execute(f"{TICKET_SELECT}{clause} ORDER BY t.created_at DESC LIMIT ? OFFSET ?", (*args, limit, offset)))
    return {"total": total, "page": page, "pages": max(1, -(-total // per_page)), "items": items}


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, db: Db = Depends(get_db)):
    if body.location_id:
        must(db, "locations", body.location_id, "Location")
    stamp = now_iso()
    data = body.model_dump(exclude={"event_id"})
    new_id = insert(db, "tickets", {**data, "created_at": stamp, "updated_at": stamp})
    if body.event_id:
        must(db, "events", body.event_id, "Event")
        db.execute("UPDATE events SET ticket_id = ? WHERE id = ?", (new_id, body.event_id))
    return one(db, f"{TICKET_SELECT} WHERE t.id = ?", (new_id,))


@router.get("/tickets/summary")
def tickets_summary(db: Db = Depends(get_db)):
    return {"by_status": {r["status"]: r["n"] for r in db.execute("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status")},
            "by_priority": {r["priority"]: r["n"] for r in db.execute("SELECT priority, COUNT(*) AS n FROM tickets GROUP BY priority")},
            "total": one(db, "SELECT COUNT(*) AS n FROM tickets")["n"]}


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, db: Db = Depends(get_db)):
    ticket = one(db, f"{TICKET_SELECT} WHERE t.id = ?", (ticket_id,))
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketPatch, db: Db = Depends(get_db)):
    must(db, "tickets", ticket_id, "Ticket")
    data = body.model_dump()
    if data.get("starred") is not None:
        data["starred"] = int(data["starred"])
    update_fields(db, "tickets", ticket_id, data, {"updated_at": now_iso()})
    return get_ticket(ticket_id, db)


@router.delete("/tickets/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int, db: Db = Depends(get_db)):
    must(db, "tickets", ticket_id, "Ticket")
    db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))


# ---------- retail analytics ----------
class FootfallIn(BaseModel):
    location_id: Optional[int] = None
    camera_id: Optional[int] = None
    ts: Optional[str] = None
    total: int = Field(ge=0)
    male: int = Field(0, ge=0)
    female: int = Field(0, ge=0)
    age_teen: int = 0
    age_young: int = 0
    age_middle: int = 0
    age_elderly: int = 0
    dwell_0_5: int = 0
    dwell_5_15: int = 0
    dwell_15_30: int = 0
    dwell_30_60: int = 0
    dwell_seconds_sum: float = 0
    transactions: int = 0
    source_job: Optional[str] = None


def add_footfall(db: Db, data: dict):
    data = {**data, "ts": data.get("ts") or now_iso()}
    return insert(db, "footfall_records", data)


@router.post("/retail/footfall", status_code=201)
def ingest_footfall(body: FootfallIn, db: Db = Depends(get_db)):
    """Store one aggregated footfall/demographics record (from the video pipeline or a live counter)."""
    return {"id": add_footfall(db, body.model_dump())}


def retail_range(start, end, location_id, default_days=15):
    today = date.today()
    last = parse_day(end, today)
    first = parse_day(start, last - timedelta(days=default_days))
    if first > last:
        raise HTTPException(400, "start must not be after end")
    loc, args = "", [first.isoformat(), last.isoformat()]
    if location_id:
        loc = " AND location_id = ?"
        args.append(location_id)
    return first, last, loc, args


@router.get("/retail/summary")
def retail_summary(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None, db: Db = Depends(get_db)):
    first, last, loc, args = retail_range(start, end, location_id)
    span = (last - first).days + 1

    def totals(a, b):
        p = [a.isoformat(), b.isoformat()] + ([location_id] if location_id else [])
        return one(db, f"""SELECT COALESCE(SUM(total),0) AS footfall, COALESCE(SUM(male),0) AS male,
                           COALESCE(SUM(female),0) AS female, COALESCE(SUM(transactions),0) AS transactions
                           FROM footfall_records WHERE date(ts) BETWEEN ? AND ?{loc}""", p)

    cur = totals(first, last)
    prev = totals(first - timedelta(days=span), first - timedelta(days=1))
    classified = cur["male"] + cur["female"]
    prev_classified = prev["male"] + prev["female"]
    conv = lambda t: round(t["transactions"] / t["footfall"] * 100, 2) if t["footfall"] else 0.0
    return {
        "start": first.isoformat(), "end": last.isoformat(), "compare_days": span,
        "footfall": {"value": cur["footfall"], "change_pct": pct_change(cur["footfall"], prev["footfall"])},
        "demographics": {"male": cur["male"], "female": cur["female"],
                         "male_pct": round(cur["male"] / classified * 100) if classified else 0,
                         "female_pct": round(cur["female"] / classified * 100) if classified else 0,
                         "male_change_pct": pct_change(cur["male"], prev["male"]),
                         "female_change_pct": pct_change(cur["female"], prev["female"])},
        "conversion": {"rate_pct": conv(cur), "transactions": cur["transactions"], "previous_rate_pct": conv(prev)},
        "previous_classified": prev_classified,
    }


@router.get("/retail/heatmap")
def retail_heatmap(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None,
                   hour_from: int = Query(10, ge=0, le=23), hour_to: int = Query(23, ge=1, le=24), db: Db = Depends(get_db)):
    first, last, loc, args = retail_range(start, end, location_id)
    cells = rows(db.execute(f"""SELECT date(ts) AS day, CAST(strftime('%H', ts) AS INTEGER) AS hour, SUM(total) AS footfall
                                FROM footfall_records WHERE date(ts) BETWEEN ? AND ?{loc}
                                AND CAST(strftime('%H', ts) AS INTEGER) >= {hour_from} AND CAST(strftime('%H', ts) AS INTEGER) < {hour_to}
                                GROUP BY day, hour ORDER BY day, hour""", args))
    days = [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]
    return {"days": days, "hours": list(range(hour_from, hour_to)), "cells": cells}


@router.get("/retail/timeseries")
def retail_timeseries(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None,
                      group: str = Query("date", pattern="^(date|hour)$"), db: Db = Depends(get_db)):
    first, last, loc, args = retail_range(start, end, location_id)
    key = "date(ts)" if group == "date" else "strftime('%H', ts)"
    points = rows(db.execute(f"""SELECT {key} AS label, SUM(total) AS total, SUM(male) AS male, SUM(female) AS female,
                                 SUM(transactions) AS transactions FROM footfall_records
                                 WHERE date(ts) BETWEEN ? AND ?{loc} GROUP BY label ORDER BY label""", args))
    if group == "date":  # fill quiet days with zeros so charts have a continuous axis
        seen = {p["label"]: p for p in points}
        points = [seen.get(d) or {"label": d, "total": 0, "male": 0, "female": 0, "transactions": 0}
                  for d in ((first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1))]
    return {"group": group, "points": points}


@router.get("/retail/age")
def retail_age(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None, db: Db = Depends(get_db)):
    first, last, loc, args = retail_range(start, end, location_id)
    s = one(db, f"""SELECT COALESCE(SUM(age_teen),0) AS teenager, COALESCE(SUM(age_young),0) AS young_adult,
                    COALESCE(SUM(age_middle),0) AS middle_age, COALESCE(SUM(age_elderly),0) AS elderly
                    FROM footfall_records WHERE date(ts) BETWEEN ? AND ?{loc}""", args)
    total = sum(s.values())
    labels = {"young_adult": "Young Adult", "middle_age": "Middle Age", "elderly": "Elderly", "teenager": "Teenager"}
    return {"total": total, "groups": [{"key": k, "label": lbl, "count": s[k], "percent": round(s[k] / total * 100, 2) if total else 0}
                                       for k, lbl in labels.items()]}


@router.get("/retail/dwell")
def retail_dwell(start: Optional[str] = None, end: Optional[str] = None, location_id: Optional[int] = None, db: Db = Depends(get_db)):
    first, last, loc, args = retail_range(start, end, location_id)
    s = one(db, f"""SELECT COALESCE(SUM(dwell_0_5),0) AS b1, COALESCE(SUM(dwell_5_15),0) AS b2, COALESCE(SUM(dwell_15_30),0) AS b3,
                    COALESCE(SUM(dwell_30_60),0) AS b4, COALESCE(SUM(dwell_seconds_sum),0) AS seconds
                    FROM footfall_records WHERE date(ts) BETWEEN ? AND ?{loc}""", args)
    count = s["b1"] + s["b2"] + s["b3"] + s["b4"]
    avg = round(s["seconds"] / count) if count else None
    return {"average_seconds": avg, "average": None if avg is None else f"{avg // 60}:{avg % 60:02d}",
            "buckets": [{"label": lbl, "count": s[k], "percent": round(s[k] / count * 100, 2) if count else 0}
                        for lbl, k in (("0-5 min", "b1"), ("5-15 min", "b2"), ("15-30 min", "b3"), ("30-60 min", "b4"))]}
