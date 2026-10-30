import time

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.db"),
            "START_COLLECTOR": False,  # tests insert samples themselves
        }
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    return resp.get_json()["token"]


@pytest.fixture
def admin_headers(client):
    return {"Authorization": f"Bearer {_login(client, 'admin', 'admin123')}"}


@pytest.fixture
def viewer_headers(client):
    return {"Authorization": f"Bearer {_login(client, 'viewer', 'viewer123')}"}


@pytest.fixture
def make_sample():
    def _make(cpu=10.0, memory=20.0, disk=30.0, ts=None):
        return {
            "ts": ts if ts is not None else time.time(),
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "load1": 0.5,
            "proc_count": 100,
        }

    return _make
