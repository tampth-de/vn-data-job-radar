"""Tests for the TopDev ingestion, using a fake HTTP server (no real network calls)."""

from datetime import date

import httpx
import pytest

from ingestion import common
from ingestion.topdev import fetch_jobs


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Skip real waiting so tests run instantly."""
    monkeypatch.setattr(common.time, "sleep", lambda seconds: None)


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


def test_empty_run_keeps_previous_partition(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "KEYWORDS", ["data"])
    partition = tmp_path / "topdev" / "dt=2026-01-02"
    partition.mkdir(parents=True)
    (partition / "_manifest.json").write_text("good", encoding="utf-8")

    real_client = httpx.Client
    monkeypatch.setattr(common, "make_client", lambda: real_client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [], "meta": {"last_page": 1}}))))

    with pytest.raises(common.SourceUnavailable):
        fetch_jobs.run(run_date=date(2026, 1, 2), raw_root=tmp_path)
    assert (partition / "_manifest.json").read_text(encoding="utf-8") == "good"


def test_run_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "KEYWORDS", ["data", "AI"])

    def handler(request: httpx.Request) -> httpx.Response:
        # Both keywords return the same job -> should be counted once as unique.
        return httpx.Response(200, json={"data": [{"id": 1}], "meta": {"last_page": 1}})

    real_client = httpx.Client
    monkeypatch.setattr(common, "make_client",
                        lambda: real_client(transport=httpx.MockTransport(handler)))

    first = fetch_jobs.run(run_date=date(2026, 1, 2), raw_root=tmp_path)
    second = fetch_jobs.run(run_date=date(2026, 1, 2), raw_root=tmp_path)

    files = list((tmp_path / "topdev" / "dt=2026-01-02").rglob("*.json"))
    assert len(files) == 3  # 2 pages + manifest, not doubled by the second run
    assert first["total_rows"] == second["total_rows"] == 2
    assert second["unique_jobs"] == 1
