import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    # Override these with environment variables in any real deployment.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me-please-0123456789")
    DATABASE = os.environ.get("DATABASE", os.path.join(BASE_DIR, "monitor.db"))

    COLLECT_INTERVAL = int(os.environ.get("COLLECT_INTERVAL", "5"))      # seconds between samples
    RETENTION_MINUTES = int(os.environ.get("RETENTION_MINUTES", "60"))   # how long samples are kept
    ALERT_COOLDOWN = int(os.environ.get("ALERT_COOLDOWN", "300"))        # seconds before the same alert repeats
    TOKEN_HOURS = int(os.environ.get("TOKEN_HOURS", "8"))

    START_COLLECTOR = True

    DEFAULT_THRESHOLDS = {"cpu": 90.0, "memory": 90.0, "disk": 90.0}
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
    VIEWER_PASSWORD = os.environ.get("VIEWER_PASSWORD", "viewer123")
