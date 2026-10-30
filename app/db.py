import sqlite3
import time
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'viewer'))
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    cpu REAL NOT NULL,
    memory REAL NOT NULL,
    disk REAL NOT NULL,
    load1 REAL NOT NULL,
    proc_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics (ts);

CREATE TABLE IF NOT EXISTS thresholds (
    metric TEXT PRIMARY KEY,
    value REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    threshold REAL NOT NULL,
    message TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts);
"""


@contextmanager
def connect(path):
    """Open a short-lived connection; commit on success, roll back on error."""
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path, default_thresholds, users):
    """Create tables and seed default thresholds and users (only if missing)."""
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        for metric, value in default_thresholds.items():
            conn.execute(
                "INSERT OR IGNORE INTO thresholds (metric, value) VALUES (?, ?)",
                (metric, value),
            )
        for username, password_hash, role in users:
            conn.execute(
                "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )


def store_sample(conn, sample, retention_minutes):
    """Insert one sample and delete samples older than the retention window."""
    conn.execute(
        "INSERT INTO metrics (ts, cpu, memory, disk, load1, proc_count) VALUES (?, ?, ?, ?, ?, ?)",
        (
            sample["ts"],
            sample["cpu"],
            sample["memory"],
            sample["disk"],
            sample["load1"],
            sample["proc_count"],
        ),
    )
    cutoff = time.time() - retention_minutes * 60
    conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
