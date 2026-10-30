import time

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash

from .alerts import METRICS, get_thresholds
from .auth import create_token, require_auth
from .collector import top_processes
from .db import connect

api = Blueprint("api", __name__, url_prefix="/api")


@api.get("/health")
def health():
    return jsonify(status="ok")


@api.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        return jsonify(error="username and password are required"), 400

    with connect(current_app.config["DATABASE"]) as conn:
        user = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?", (username,)
        ).fetchone()

    # Same error for unknown user and wrong password, so usernames can't be probed.
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Invalid credentials"), 401

    token = create_token(
        user["username"], user["role"], current_app.config["SECRET_KEY"], current_app.config["TOKEN_HOURS"]
    )
    return jsonify(token=token, username=user["username"], role=user["role"])


@api.get("/metrics/latest")
@require_auth()
def latest_metrics():
    with connect(current_app.config["DATABASE"]) as conn:
        row = conn.execute("SELECT * FROM metrics ORDER BY ts DESC LIMIT 1").fetchone()
    if row is None:
        return jsonify(error="No samples collected yet"), 404
    return jsonify(dict(row))


@api.get("/metrics/history")
@require_auth()
def metrics_history():
    try:
        minutes = int(request.args.get("minutes", 30))
    except ValueError:
        return jsonify(error="minutes must be an integer"), 400
    minutes = max(1, min(minutes, 1440))
    since = time.time() - minutes * 60
    with connect(current_app.config["DATABASE"]) as conn:
        rows = conn.execute(
            "SELECT ts, cpu, memory, disk, load1, proc_count FROM metrics WHERE ts >= ? ORDER BY ts ASC",
            (since,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@api.get("/processes")
@require_auth()
def processes():
    sort_by = request.args.get("sort", "memory")
    if sort_by not in ("memory", "cpu"):
        return jsonify(error="sort must be 'memory' or 'cpu'"), 400
    return jsonify(top_processes(limit=10, sort_by=sort_by))


@api.get("/alerts")
@require_auth()
def list_alerts():
    with connect(current_app.config["DATABASE"]) as conn:
        rows = conn.execute("SELECT * FROM alerts ORDER BY ts DESC LIMIT 50").fetchall()
    return jsonify([dict(r) for r in rows])


@api.post("/alerts/<int:alert_id>/ack")
@require_auth(role="admin")
def ack_alert(alert_id):
    with connect(current_app.config["DATABASE"]) as conn:
        cur = conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    if cur.rowcount == 0:
        return jsonify(error="Alert not found"), 404
    return jsonify(status="acknowledged", id=alert_id)


@api.get("/thresholds")
@require_auth()
def read_thresholds():
    with connect(current_app.config["DATABASE"]) as conn:
        return jsonify(get_thresholds(conn))


@api.put("/thresholds")
@require_auth(role="admin")
def update_thresholds():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify(error="Send a JSON object like {\"cpu\": 80}"), 400

    cleaned = {}
    for metric, value in data.items():
        if metric not in METRICS:
            return jsonify(error=f"Unknown metric '{metric}'"), 400
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 100:
            return jsonify(error=f"Threshold for '{metric}' must be a number between 1 and 100"), 400
        cleaned[metric] = float(value)

    with connect(current_app.config["DATABASE"]) as conn:
        for metric, value in cleaned.items():
            conn.execute("UPDATE thresholds SET value = ? WHERE metric = ?", (value, metric))
        return jsonify(get_thresholds(conn))
