# Server Monitor

A small web dashboard that watches a Linux server's health. A background collector samples CPU, memory, disk, load average and process count every few seconds, stores the history, raises alerts when a metric crosses a threshold, and shows everything on a live dashboard behind a login.

Built with Python (Flask, psutil), SQLite, JWT authentication and role-based access control, and a plain JavaScript + Chart.js frontend.

> Add 2-3 screenshots here after you run it (login page, dashboard, alerts). Save them in a `docs/` folder and link them.

## Features

- **Collector**: background thread reads system stats with `psutil` (which reads `/proc` on Linux) at a configurable interval.
- **History**: samples are stored in SQLite and automatically pruned after a retention window (default 60 min).
- **Alerts**: when CPU, memory or disk goes above its threshold, an alert is created. A cooldown stops the same alert from repeating every few seconds while it is unacknowledged.
- **Top processes**: shows the busiest processes, sortable by memory or CPU.
- **Auth**: login returns a signed JWT. Passwords are stored as salted hashes.
- **Roles**: `admin` can change thresholds and acknowledge alerts. `viewer` is read-only.
- **Tests**: 23 pytest tests covering auth, roles, validation, retention, alerts and the collector.

## Architecture

```
 Browser (HTML/JS + Chart.js)
        |  fetch() with  Authorization: Bearer <JWT>
        v
 Flask REST API  ----------------------------+
   auth.py   (JWT check, role check)         |
   routes.py (endpoints, validation)         |
        |                                    |
        v                                    v
   SQLite (users, metrics,            Collector thread
   thresholds, alerts)  <-----------  psutil -> sample -> store -> check thresholds
```

```
app/
  __init__.py   app factory, seeds users/thresholds, starts the collector
  config.py     settings (all overridable with environment variables)
  db.py         SQLite schema, connection helper, sample storage + pruning
  collector.py  psutil sampling, top processes, background thread
  alerts.py     threshold checks with cooldown
  auth.py       JWT creation and the @require_auth(role=...) decorator
  routes.py     REST endpoints
  static/       index.html, app.js, style.css
tests/          pytest suite
```

## Run it locally

Works on Linux, macOS, Windows, and WSL (Ubuntu). Python 3.10+.

```bash
git clone <your-repo-url>
cd server-monitor
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://localhost:5000 and sign in:

| User   | Password    | Role   |
|--------|-------------|--------|
| admin  | admin123    | admin  |
| viewer | viewer123   | viewer |

These are demo defaults. Change them (and the signing key) before running anywhere real:

```bash
export SECRET_KEY="a-long-random-string"
export ADMIN_PASSWORD="something-strong"
export VIEWER_PASSWORD="something-else"
python run.py
```

Users are created on first start only, so delete `monitor.db` after changing the passwords.

### Docker

```bash
docker build -t server-monitor .
docker run -p 5000:5000 -v monitor-data:/data \
  -e SECRET_KEY=change-me -e ADMIN_PASSWORD=change-me -e VIEWER_PASSWORD=change-me \
  server-monitor
```

Note: inside a container, `psutil` reports what the container can see, which can differ from the host.

### Tests

```bash
pytest -q
```

## API

All routes except `/api/health` and `/api/auth/login` need `Authorization: Bearer <token>`.

| Method | Path                       | Role   | Description                              |
|--------|----------------------------|--------|------------------------------------------|
| GET    | `/api/health`              | public | Liveness check                           |
| POST   | `/api/auth/login`          | public | `{username, password}` -> `{token, role}` |
| GET    | `/api/metrics/latest`      | any    | Most recent sample                       |
| GET    | `/api/metrics/history`     | any    | `?minutes=30` (1-1440), oldest first     |
| GET    | `/api/processes`           | any    | Top 10, `?sort=memory` or `cpu`          |
| GET    | `/api/alerts`              | any    | Latest 50 alerts                         |
| POST   | `/api/alerts/<id>/ack`     | admin  | Acknowledge an alert                     |
| GET    | `/api/thresholds`          | any    | Current thresholds                       |
| PUT    | `/api/thresholds`          | admin  | e.g. `{"cpu": 80, "memory": 85}`         |

Quick try from a terminal:

```bash
TOKEN=$(curl -s -X POST localhost:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

curl -s localhost:5000/api/metrics/latest -H "Authorization: Bearer $TOKEN"
```

To see an alert fire, lower a threshold: `PUT /api/thresholds` with `{"cpu": 1}`.

## Design decisions

- **SQLite** keeps setup to zero. The SQL is plain and isolated in `db.py`, `alerts.py` and `routes.py`, so moving to MySQL or PostgreSQL means changing the connection layer and a few type details.
- **One short-lived DB connection per operation** avoids sharing connections between the collector thread and request threads.
- **Same error for unknown user and wrong password**, so usernames cannot be guessed from the response.
- **Frontend uses `textContent`, not `innerHTML`**, because process names come from the system and should be treated as untrusted.
- **Alert cooldown** prevents hundreds of duplicate alerts during a sustained spike.
- **Single gunicorn worker**: the collector runs inside the app process, so more workers would duplicate samples. A larger design would move the collector into its own service.

## Known limitations

- No login rate limiting or account lockout.
- Tokens live in `sessionStorage` and cannot be revoked before they expire.
- Monitors one machine only (the one it runs on), no agents for remote hosts.
- Alerts appear on the dashboard only; there is no email or webhook notification.

## Ideas to extend

- Per-core CPU and network I/O charts.
- Webhook or email notifications for alerts.
- Switch storage to MySQL.
- Agent mode: small collectors on several servers posting to one API.
