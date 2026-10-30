import time

from app.alerts import check_thresholds
from app.collector import collect_sample, top_processes
from app.db import connect, store_sample


# ---------- authentication ----------

def test_health_is_public(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_login_success_returns_token_and_role(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["role"] == "admin" and body["token"]


def test_login_wrong_password_is_rejected(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_login_unknown_user_gets_same_error(client):
    resp = client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Invalid credentials"


def test_login_requires_fields(client):
    assert client.post("/api/auth/login", json={}).status_code == 400


def test_protected_route_needs_token(client):
    assert client.get("/api/metrics/latest").status_code == 401


def test_invalid_token_is_rejected(client):
    resp = client.get("/api/metrics/latest", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# ---------- role-based access control ----------

def test_viewer_cannot_change_thresholds(client, viewer_headers):
    resp = client.put("/api/thresholds", json={"cpu": 50}, headers=viewer_headers)
    assert resp.status_code == 403


def test_admin_can_change_thresholds(client, admin_headers):
    resp = client.put("/api/thresholds", json={"cpu": 55}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.get_json()["cpu"] == 55.0


def test_threshold_validation(client, admin_headers):
    assert client.put("/api/thresholds", json={"cpu": 500}, headers=admin_headers).status_code == 400
    assert client.put("/api/thresholds", json={"gpu": 50}, headers=admin_headers).status_code == 400
    assert client.put("/api/thresholds", json={"cpu": "high"}, headers=admin_headers).status_code == 400


def test_viewer_cannot_ack_alert(client, viewer_headers):
    assert client.post("/api/alerts/1/ack", headers=viewer_headers).status_code == 403


# ---------- metrics ----------

def test_latest_404_when_no_samples(client, viewer_headers):
    assert client.get("/api/metrics/latest", headers=viewer_headers).status_code == 404


def test_latest_and_history_return_stored_samples(app, client, viewer_headers, make_sample):
    with connect(app.config["DATABASE"]) as conn:
        store_sample(conn, make_sample(cpu=11.0, ts=time.time() - 10), 60)
        store_sample(conn, make_sample(cpu=22.0), 60)

    latest = client.get("/api/metrics/latest", headers=viewer_headers).get_json()
    assert latest["cpu"] == 22.0

    history = client.get("/api/metrics/history?minutes=5", headers=viewer_headers).get_json()
    assert [row["cpu"] for row in history] == [11.0, 22.0]  # oldest first


def test_history_excludes_old_samples(app, client, viewer_headers, make_sample):
    with connect(app.config["DATABASE"]) as conn:
        store_sample(conn, make_sample(ts=time.time() - 3 * 3600), 600)
    history = client.get("/api/metrics/history?minutes=30", headers=viewer_headers).get_json()
    assert history == []


def test_history_rejects_bad_minutes(client, viewer_headers):
    assert client.get("/api/metrics/history?minutes=abc", headers=viewer_headers).status_code == 400


def test_retention_prunes_old_rows(app, make_sample):
    with connect(app.config["DATABASE"]) as conn:
        store_sample(conn, make_sample(ts=time.time() - 7200), 1000)  # old but kept by big window
        store_sample(conn, make_sample(), 60)                          # 60 min window prunes it
        count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    assert count == 1


# ---------- alerts ----------

def test_alert_created_when_threshold_exceeded(app, client, viewer_headers, make_sample):
    with connect(app.config["DATABASE"]) as conn:
        created = check_thresholds(conn, make_sample(cpu=95.0))
    assert len(created) == 1 and "CPU" in created[0]

    alerts = client.get("/api/alerts", headers=viewer_headers).get_json()
    assert len(alerts) == 1 and alerts[0]["acknowledged"] == 0


def test_no_alert_below_threshold(app, make_sample):
    with connect(app.config["DATABASE"]) as conn:
        assert check_thresholds(conn, make_sample(cpu=50.0)) == []


def test_alert_cooldown_prevents_flooding(app, make_sample):
    with connect(app.config["DATABASE"]) as conn:
        first = check_thresholds(conn, make_sample(cpu=95.0, ts=1000.0), cooldown=300)
        second = check_thresholds(conn, make_sample(cpu=96.0, ts=1010.0), cooldown=300)
        later = check_thresholds(conn, make_sample(cpu=97.0, ts=1400.0), cooldown=300)
    assert len(first) == 1
    assert second == []        # inside cooldown, still unacknowledged
    assert len(later) == 1     # cooldown passed


def test_admin_can_acknowledge_alert(app, client, admin_headers, make_sample):
    with connect(app.config["DATABASE"]) as conn:
        check_thresholds(conn, make_sample(memory=99.0))
    alert_id = client.get("/api/alerts", headers=admin_headers).get_json()[0]["id"]

    assert client.post(f"/api/alerts/{alert_id}/ack", headers=admin_headers).status_code == 200
    assert client.get("/api/alerts", headers=admin_headers).get_json()[0]["acknowledged"] == 1
    assert client.post("/api/alerts/9999/ack", headers=admin_headers).status_code == 404


# ---------- real system data ----------

def test_collect_sample_returns_sane_values():
    sample = collect_sample()
    for key in ("cpu", "memory", "disk"):
        assert 0 <= sample[key] <= 100
    assert sample["proc_count"] > 0


def test_top_processes_shape_and_sorting():
    procs = top_processes(limit=5, sort_by="memory")
    assert 0 < len(procs) <= 5
    assert {"pid", "name", "cpu", "memory"} <= set(procs[0])
    memory_values = [p["memory"] for p in procs]
    assert memory_values == sorted(memory_values, reverse=True)


def test_processes_endpoint(client, viewer_headers):
    resp = client.get("/api/processes?sort=cpu", headers=viewer_headers)
    assert resp.status_code == 200 and isinstance(resp.get_json(), list)
    assert client.get("/api/processes?sort=bad", headers=viewer_headers).status_code == 400
