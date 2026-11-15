"""Tests for the TopDev ingestion, using a fake HTTP server (no real network calls)."""

import httpx
import pytest

from ingestion.topdev import fetch_jobs


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Skip real waiting so tests run instantly."""
    monkeypatch.setattr(fetch_jobs.time, "sleep", lambda seconds: None)


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_keyword_follows_all_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, json={
            "data": [{"id": page * 10 + 1}, {"id": page * 10 + 2}],
            "meta": {"current_page": page, "last_page": 3},
        })

    pages = fetch_jobs.fetch_keyword(make_client(handler), "data")

    assert len(pages) == 3
    assert [p["meta"]["current_page"] for p in pages] == [1, 2, 3]


def test_fetch_page_retries_on_server_error():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(500)
        return httpx.Response(200, json={"data": [], "meta": {"last_page": 1}})

    data = fetch_jobs.fetch_page(make_client(handler), "data", 1)

    assert calls["n"] == 3
    assert data["meta"]["last_page"] == 1


def test_fetch_page_does_not_retry_on_client_error():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        fetch_jobs.fetch_page(make_client(handler), "data", 1)
    assert calls["n"] == 1


def test_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "RAW_DIR", tmp_path)
    monkeypatch.setattr(fetch_jobs, "KEYWORDS", ["data", "AI"])

    def handler(request: httpx.Request) -> httpx.Response:
        # Both keywords return the same job -> should be counted once as unique.
        return httpx.Response(200, json={"data": [{"id": 1}], "meta": {"last_page": 1}})

    real_client = httpx.Client
    monkeypatch.setattr(
        fetch_jobs.httpx, "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )

    first = fetch_jobs.run()
    second = fetch_jobs.run()

    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.json"))
    assert len(files) == 3  # 2 pages + manifest, not doubled by the second run
    assert first["total_rows"] == second["total_rows"] == 2
    assert second["unique_jobs"] == 1
