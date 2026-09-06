import asyncio
import logging
import threading

import pytest
from fastapi.testclient import TestClient

import config
from dashboard import create_app, start_dashboard
from database import add_pending, add_warning, connect

TOKEN = "s3cret-token"


@pytest.fixture
def client():
    return TestClient(create_app(TOKEN))


def test_empty_token_is_refused():
    with pytest.raises(ValueError):
        create_app("")


@pytest.mark.parametrize("path", ["/infractions", "/appeals", "/pending"])
def test_data_routes_require_a_bearer_token(client, path):
    r = client.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get(path, headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401


def test_health_needs_no_token(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_infractions_returns_objects_not_tuples(client):
    add_warning(5, 1)
    add_warning(5, 1)
    add_warning(6, 1)
    r = client.get("/infractions", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert r.json() == [
        {"user_id": 5, "guild_id": 1, "count": 2},
        {"user_id": 6, "guild_id": 1, "count": 1},
    ]


def test_pending_lists_only_pending_rows(client):
    pid = add_pending(1, 5, 4, "ban", "hate")
    r = client.get("/pending", headers={"Authorization": f"Bearer {TOKEN}"})
    assert [row["id"] for row in r.json()] == [pid]
    assert r.json()[0]["action"] == "ban"


def test_default_host_is_loopback():
    assert config.DASHBOARD_HOST == "127.0.0.1"


def test_start_dashboard_without_token_does_not_start(caplog):
    caplog.set_level(logging.WARNING)
    assert start_dashboard(token="", host="127.0.0.1", port=8000) is None
    assert "DASHBOARD_TOKEN" in caplog.text


async def test_start_dashboard_creates_one_task_from_the_factory():
    served = []

    class FakeServer:
        def __init__(self, app, host, port):
            self.args = (host, port)

        async def serve(self):
            served.append(self.args)

    task = start_dashboard(token=TOKEN, host="127.0.0.1", port=0, server_factory=FakeServer)
    assert isinstance(task, asyncio.Task)
    await task
    assert served == [("127.0.0.1", 0)]


def test_two_threads_interleave_reads_and_writes_without_error():
    errors: list[BaseException] = []

    def worker(uid: int) -> None:
        try:
            for _ in range(50):
                add_warning(uid, 1)
                with connect() as conn:
                    conn.execute("SELECT * FROM warnings").fetchall()
        except BaseException as exc:  # noqa: BLE001 — collecting for the assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with connect() as conn:
        counts = {r["user_id"]: r["count"] for r in conn.execute("SELECT * FROM warnings")}
    assert counts == {0: 50, 1: 50}
