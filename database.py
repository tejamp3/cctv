"""SQLite storage for the VS corp CCTV retail analytics backend."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "runtime" / "vscorp.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS cameras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'RTSP',
    rtsp_url TEXT,
    status TEXT NOT NULL DEFAULT 'offline',
    codec TEXT,
    bitrate_kbps REAL,
    resolution TEXT,
    last_seen TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    start_ts TEXT NOT NULL,
    end_ts TEXT,
    file_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    ts TEXT NOT NULL,
    result TEXT,
    image_url TEXT,
    recording_id INTEGER REFERENCES recordings(id) ON DELETE SET NULL,
    important INTEGER NOT NULL DEFAULT 0,
    ticket_id INTEGER
);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS attendance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('in', 'out')),
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT NOT NULL DEFAULT 'medium',
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    starred INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS footfall_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
    ts TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    male INTEGER NOT NULL DEFAULT 0,
    female INTEGER NOT NULL DEFAULT 0,
    age_teen INTEGER NOT NULL DEFAULT 0,
    age_young INTEGER NOT NULL DEFAULT 0,
    age_middle INTEGER NOT NULL DEFAULT 0,
    age_elderly INTEGER NOT NULL DEFAULT 0,
    dwell_0_5 INTEGER NOT NULL DEFAULT 0,
    dwell_5_15 INTEGER NOT NULL DEFAULT 0,
    dwell_15_30 INTEGER NOT NULL DEFAULT 0,
    dwell_30_60 INTEGER NOT NULL DEFAULT 0,
    dwell_seconds_sum REAL NOT NULL DEFAULT 0,
    transactions INTEGER NOT NULL DEFAULT 0,
    source_job TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_footfall_ts ON footfall_records(ts);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON attendance_logs(ts);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def get_db():
    """FastAPI dependency: one connection per request."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
