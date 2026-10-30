import atexit
import os

from flask import Flask, send_from_directory
from werkzeug.security import generate_password_hash

from .collector import Collector
from .config import Config
from .db import init_db
from .routes import api


def create_app(overrides=None):
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    app = Flask(__name__, static_folder=static_dir, static_url_path="/static")
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)

    # Passwords are stored as salted hashes, never in plain text.
    users = [
        ("admin", generate_password_hash(app.config["ADMIN_PASSWORD"]), "admin"),
        ("viewer", generate_password_hash(app.config["VIEWER_PASSWORD"]), "viewer"),
    ]
    init_db(app.config["DATABASE"], app.config["DEFAULT_THRESHOLDS"], users)

    app.register_blueprint(api)

    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    if app.config["START_COLLECTOR"]:
        collector = Collector(
            app.config["DATABASE"],
            app.config["COLLECT_INTERVAL"],
            app.config["RETENTION_MINUTES"],
            app.config["ALERT_COOLDOWN"],
        )
        collector.start()
        atexit.register(collector.stop)
        app.collector = collector

    return app
