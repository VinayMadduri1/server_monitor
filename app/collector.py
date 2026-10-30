import logging
import os
import threading
import time

import psutil

from .alerts import check_thresholds
from .db import connect, store_sample

log = logging.getLogger(__name__)


def collect_sample():
    """Read current system stats using psutil (reads /proc on Linux)."""
    load1 = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    return {
        "ts": time.time(),
        "cpu": psutil.cpu_percent(interval=0.2),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage(os.path.abspath(os.sep)).percent,
        "load1": round(load1, 2),
        "proc_count": len(psutil.pids()),
    }


def top_processes(limit=10, sort_by="memory"):
    """Return the busiest processes. sort_by is 'memory' or 'cpu'."""
    key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
    rows = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        info = proc.info
        rows.append(
            {
                "pid": info["pid"],
                "name": info["name"] or "?",
                "cpu": round(info["cpu_percent"] or 0.0, 1),
                "memory": round(info["memory_percent"] or 0.0, 1),
            }
        )
    rows.sort(key=lambda r: r["cpu" if key == "cpu_percent" else "memory"], reverse=True)
    return rows[:limit]


class Collector:
    """Background thread: sample -> store -> check thresholds, every `interval` seconds."""

    def __init__(self, db_path, interval, retention_minutes, cooldown):
        self.db_path = db_path
        self.interval = interval
        self.retention_minutes = retention_minutes
        self.cooldown = cooldown
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="collector", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def run_once(self):
        sample = collect_sample()
        with connect(self.db_path) as conn:
            store_sample(conn, sample, self.retention_minutes)
            check_thresholds(conn, sample, self.cooldown)
        return sample

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("collector iteration failed")
            self._stop.wait(self.interval)
