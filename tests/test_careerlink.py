"""Tests for CareerLink parsing and polite fetching (fake HTTP server, no network)."""

import json
from datetime import date

import httpx
import pytest

from ingestion import common
from ingestion.careerlink import fetch_jobs
from ingestion.careerlink.parse import extract_job_posting, looks_relevant, parse_job_links, parse_total


def search_page(jobs: dict[int, str], total: int | None = None) -> str:
    links = "".join(
        f'<a href="/tim-viec-lam/job-{i}/{i}"><img alt="logo"></a>'   # logo link, no text
        f'<a href="/tim-viec-lam/job-{i}/{i}">Mới  {title}</a>'       # title link with "new" badge
        for i, title in jobs.items()
    )
    count = total if total is not None else len(jobs)
    return f"<html><body><p>{count} việc làm</p>{links}<a href='/vieclam/list'>x</a></body></html>"


def job_page(posting: dict | None) -> str:
    ld = f'<script type="application/ld+json">{json.dumps(posting)}</script>' if posting else ""
    return f"<html><head><title>CareerLink</title>{ld}</head><body></body></html>"


POSTING = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Data Engineer",
           "baseSalary": {"@type": "MonetaryAmount", "currency": "VND",
                          "value": {"minValue": 20000000, "maxValue": 30000000, "unitText": "MONTH"}}}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    monkeypatch.setattr(fetch_jobs.time, "sleep", lambda s: None)


# --- parsing -------------------------------------------------------------------------

def test_parse_job_links_keeps_title_link_and_strips_badge():
    jobs = parse_job_links(search_page({11: "Data Engineer", 12: "Kế toán"}))
    assert jobs == {11: ("/tim-viec-lam/job-11/11", "Data Engineer"),
                    12: ("/tim-viec-lam/job-12/12", "Kế toán")}


def test_parse_total():
    assert parse_total(search_page({}, total=2231)) == 2231
    assert parse_total("<p>1.234 việc làm</p>") == 1234


@pytest.mark.parametrize("title, expected", [
    ("KỸ SƯ DỮ LIỆU", True),
    ("Edge AI Engineer", True),
    ("Chuyên Viên ESG (Data Analyst)", True),
    ("Power Platform & BI Developer", True),
    ("Điều Dưỡng Nội Khoa", False),
    ("Nhân Viên Kế Toán Tổng Hợp", False),
    ("Chuyên viên Mua hàng (MRO)", False),   # "mua" must not match "ai"-like patterns
])
def test_looks_relevant(title, expected):
    assert looks_relevant(title) is expected


def test_extract_job_posting_handles_graph_and_absence():
    graph = {"@context": "https://schema.org", "@graph": [{"@type": "Organization"}, POSTING]}
    assert extract_job_posting(job_page(graph))["title"] == "Data Engineer"
    assert extract_job_posting(job_page(None)) is None
    assert extract_job_posting('<script type="application/ld+json">{not json</script>') is None


# --- fetching ------------------------------------------------------------------------

def patch_client(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(common, "make_client", lambda: real_client(transport=httpx.MockTransport(handler)))


def test_run_fetches_only_new_relevant_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "KEYWORDS", ["data engineer"])
    requested_jobs = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vieclam/list":
            return httpx.Response(200, text=search_page({1: "Data Engineer", 2: "Điều dưỡng", 3: "AI Engineer"}))
        requested_jobs.append(int(request.url.path.rsplit("/", 1)[1]))
        return httpx.Response(200, text=job_page(POSTING))

    patch_client(monkeypatch, handler)
    jobs_dir = tmp_path / "careerlink" / "jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "3.json").write_text("{}", encoding="utf-8")   # job 3 already known

    manifest = fetch_jobs.run(run_date=date(2026, 1, 1), raw_root=tmp_path)

    assert requested_jobs == [1]                  # 2 is irrelevant, 3 already fetched
    assert manifest["unique_jobs"] == 3           # all three are still in today's snapshot
    assert manifest["relevant_jobs"] == 2
    saved = json.loads((jobs_dir / "1.json").read_text(encoding="utf-8"))
    assert saved["job_posting"]["title"] == "Data Engineer"
    assert saved["first_keywords"] == ["data engineer"]
    assert (tmp_path / "careerlink" / "dt=2026-01-01" / "keyword=data engineer" / "page_001.html").exists()


def test_circuit_breaker_stops_when_pages_come_back_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "KEYWORDS", ["data"])
    requested_jobs = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vieclam/list":
            return httpx.Response(200, text=search_page({i: f"Data job {i}" for i in range(1, 11)}))
        requested_jobs.append(request.url.path)
        return httpx.Response(200, text=job_page(None))   # site serves pages without data

    patch_client(monkeypatch, handler)
    manifest = fetch_jobs.run(run_date=date(2026, 1, 1), raw_root=tmp_path)

    assert len(requested_jobs) == fetch_jobs.MAX_CONSECUTIVE_MISSING
    assert manifest["details"]["stopped_early"] is True
    assert manifest["details"]["saved"] == []


def test_detail_fetches_are_capped_per_run(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_jobs, "KEYWORDS", ["data"])
    monkeypatch.setattr(fetch_jobs, "MAX_DETAILS_PER_RUN", 4)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vieclam/list":
            return httpx.Response(200, text=search_page({i: f"Data job {i}" for i in range(1, 11)}))
        return httpx.Response(200, text=job_page(POSTING))

    patch_client(monkeypatch, handler)
    manifest = fetch_jobs.run(run_date=date(2026, 1, 1), raw_root=tmp_path)

    assert len(manifest["details"]["saved"]) == 4
    assert manifest["details"]["remaining"] == 6   # picked up by the next run
