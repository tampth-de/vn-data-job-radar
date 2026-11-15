"""Tests for ITviec parsing and paging, using a synthetic HTML fixture (no network)."""

from datetime import date
from pathlib import Path

import httpx
import pytest

from ingestion import common
from ingestion.itviec import fetch_jobs
from ingestion.itviec.parse import parse_job_cards, parse_total

FIXTURE = (Path(__file__).parent / "fixtures" / "itviec_listing.html").read_text(encoding="utf-8")
EMPTY_PAGE = "<html><body><h1>0 jobs</h1></body></html>"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda seconds: None)


def test_parse_total():
    assert parse_total(FIXTURE) == 21
    assert parse_total("<h1>1,234 AI jobs in Vietnam</h1>") == 1234
    assert parse_total("<p>no heading</p>") is None


def test_parse_job_cards_full_card():
    jobs = parse_job_cards(FIXTURE)
    assert len(jobs) == 2

    job = jobs[0]
    assert job["job_slug"] == "senior-data-engineer-acme-1234"
    assert job["title"] == "Senior Data Engineer (Spark, Airflow)"
    assert job["url"] == "https://itviec.com/it-jobs/senior-data-engineer-acme-1234"
    assert job["company_name"] == "Acme"
    assert job["company_legal_name"] == "Acme Vietnam Co., Ltd"
    assert job["company_slug"] == "acme"
    assert job["posted_text"] == "3 days ago"
    assert job["salary_text"] is None  # hidden behind login
    assert job["work_mode"] == "Hybrid"
    assert job["location"] == "Ho Chi Minh"
    assert job["categories"] == ["Data Engineer"]
    assert job["skills"] == ["Spark", "Airflow", "SQL"]
    assert job["labels"] == ["SUPER HOT"]


def test_parse_job_cards_handles_missing_fields():
    job = parse_job_cards(FIXTURE)[1]
    assert job["salary_text"] == "1,000 - 2,000 USD"  # visible salary is kept
    assert job["company_legal_name"] is None
    assert job["skills"] == []
    assert job["labels"] == []
    assert job["posted_text"] == "5 hours ago"


def _patch_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(common, "make_client",
                        lambda: real_client(transport=httpx.MockTransport(handler)))


def test_fetch_category_stops_at_last_page(monkeypatch):
    requested_pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", 1))
        requested_pages.append(page)
        return httpx.Response(200, text=FIXTURE)  # total=21 -> 2 pages

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pages = fetch_jobs.fetch_category(client, "data-engineer")

    assert requested_pages == [1, 2]
    assert len(pages) == 2


def test_fetch_category_stops_on_empty_page(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, text=FIXTURE if page == 1 else EMPTY_PAGE)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        pages = fetch_jobs.fetch_category(client, "data-engineer")

    assert len(pages) == 1


def test_run_writes_partition_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "CATEGORIES", ["data-engineer", "ai"])
    single_page = FIXTURE.replace("21 data engineer jobs", "2 data engineer jobs")
    _patch_client(monkeypatch, lambda request: httpx.Response(200, text=single_page))

    manifest = fetch_jobs.run(run_date=date(2026, 1, 2), raw_root=tmp_path)
    fetch_jobs.run(run_date=date(2026, 1, 2), raw_root=tmp_path)  # re-run: idempotent

    out = tmp_path / "itviec" / "dt=2026-01-02"
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.*"))
    assert files == [
        "_manifest.json",
        "category=ai/page_001.html",
        "category=data-engineer/page_001.html",
    ]
    assert manifest["total_rows"] == 4   # 2 jobs x 2 categories
    assert manifest["unique_jobs"] == 2  # same jobs in both categories
