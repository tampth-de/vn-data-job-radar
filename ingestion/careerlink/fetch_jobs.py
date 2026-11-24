"""Fetch Data/AI job postings from CareerLink and save the raw responses.

Two kinds of raw data, kept apart on purpose:

  * daily search snapshot (cheap, ~10 requests): which jobs are listed today
        data/raw/careerlink/dt=YYYY-MM-DD/keyword=<kw>/page_001.html
        data/raw/careerlink/dt=YYYY-MM-DD/_manifest.json
  * job details, fetched ONCE per job (incremental enrichment):
        data/raw/careerlink/jobs/<job_id>.json
            {"job_id", "url", "first_keywords", "fetched_at", "job_posting": {...}}

Being a good citizen: during the first test run the site started serving empty pages
after ~40 job pages in a row, so details are fetched slowly (5 s apart), capped per
run, and the run stops as soon as pages come back without data (circuit breaker).
Jobs not fetched today are simply picked up on the next run.

Terms review: CareerLink claims rights over its interface, code and brand; job ads
belong to the employers. Its terms forbid overloading the site and collecting
personal data, neither of which we do (see docs/source_survey.md).
"""

import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from ingestion import common
from ingestion.careerlink.parse import extract_job_posting, looks_relevant, parse_job_links, parse_total

SOURCE = "careerlink"
BASE_URL = "https://www.careerlink.vn"
SEARCH_PATH = "/vieclam/list"
JOBS_PER_PAGE = 50
MAX_PAGES = 3

DETAIL_PAUSE_S = 5.0
MAX_DETAILS_PER_RUN = 40
MAX_CONSECUTIVE_MISSING = 3

# Precise phrases only: CareerLink searches the full ad text, so broad terms
# ("data", "power bi", "trí tuệ nhân tạo") return hundreds of unrelated jobs.
# The title classifier in dbt removes what is still off-topic.
KEYWORDS = [
    "data engineer",
    "kỹ sư dữ liệu",
    "data analyst",
    "phân tích dữ liệu",
    "data analytics",
    "data scientist",
    "business intelligence",
    "big data",
    "machine learning",
    "AI engineer",
]

log = logging.getLogger(__name__)


def search_keyword(client: httpx.Client, keyword: str) -> list[tuple[str, dict[int, tuple[str, str]]]]:
    """Return [(html, {job_id: (path, title)}), ...] for every result page of a keyword."""
    pages = []
    page = 1
    last_page = 1
    while page <= MAX_PAGES:
        params = {"keyword": keyword, **({"page": page} if page > 1 else {})}
        html = common.get_with_retries(client, BASE_URL + SEARCH_PATH, params=params).text
        jobs = parse_job_links(html)
        if page == 1:
            total = parse_total(html) or len(jobs)
            last_page = max(1, -(-total // JOBS_PER_PAGE))  # ceil division
        if not jobs and page > 1:
            break
        pages.append((html, jobs))
        log.info("keyword=%r page %d/%d: %d jobs", keyword, page, last_page, len(jobs))
        if page >= last_page:
            break
        page += 1
        common.polite_pause()
    return pages


def known_job_ids(jobs_dir: Path) -> set[int]:
    return {int(p.stem) for p in jobs_dir.glob("*.json")} if jobs_dir.exists() else set()


def fetch_new_details(client: httpx.Client, todo: dict[int, tuple[str, list[str]]], jobs_dir: Path) -> dict:
    """Fetch JobPosting JSON-LD for new jobs, slowly, with a cap and a circuit breaker.

    `todo` maps job_id -> (path, keywords that found it).
    """
    saved, missing, consecutive_missing, stopped_early = [], [], 0, False
    for n, (job_id, (path, keywords)) in enumerate(sorted(todo.items())):
        if n >= MAX_DETAILS_PER_RUN:
            break
        time.sleep(DETAIL_PAUSE_S)
        posting = extract_job_posting(common.get_with_retries(client, BASE_URL + path).text)
        if posting is None:
            missing.append(job_id)
            consecutive_missing += 1
            if consecutive_missing >= MAX_CONSECUTIVE_MISSING:
                log.warning("%d job pages in a row without data: the site is probably limiting us, "
                            "stopping for today", consecutive_missing)
                stopped_early = True
                break
            continue
        consecutive_missing = 0
        common.write_json(jobs_dir / f"{job_id}.json", {
            "job_id": job_id,
            "url": BASE_URL + path,
            "first_keywords": keywords,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "job_posting": posting,
        })
        saved.append(job_id)
    return {"saved": saved, "missing": missing, "stopped_early": stopped_early,
            "remaining": max(0, len(todo) - len(saved) - len(missing))}


def run(run_date: date | None = None, raw_root: Path | None = None) -> dict:
    run_date = run_date or date.today()
    out_dir = common.reset_partition(SOURCE, run_date, raw_root)
    jobs_dir = out_dir.parent / "jobs"
    started_at = datetime.now(timezone.utc)
    per_keyword: dict[str, dict] = {}
    listed: dict[int, tuple[str, list[str]]] = {}   # job_id -> (path, keywords)
    titles: dict[int, str] = {}

    with common.make_client() as client:
        for i, keyword in enumerate(KEYWORDS):
            if i > 0:
                common.polite_pause()
            pages = search_keyword(client, keyword)
            found = set()
            for page_no, (html, jobs) in enumerate(pages, start=1):
                common.write_text(out_dir / f"keyword={keyword}" / f"page_{page_no:03d}.html", html)
                found.update(jobs)
                for job_id, (path, title) in jobs.items():
                    listed.setdefault(job_id, (path, []))[1].append(keyword)
                    titles.setdefault(job_id, title)
            per_keyword[keyword] = {"pages": len(pages), "jobs": len(found)}

        known = known_job_ids(jobs_dir)
        relevant = {job_id for job_id in listed if looks_relevant(titles.get(job_id, ""))}
        todo = {job_id: listed[job_id] for job_id in relevant if job_id not in known}
        details = fetch_new_details(client, todo, jobs_dir)
        log.info("listed today: %d jobs, %d look relevant (%d already known); details fetched: %d, "
                 "without data: %d, left for next run: %d", len(listed), len(relevant),
                 len(relevant) - len(todo), len(details["saved"]), len(details["missing"]),
                 details["remaining"])

    manifest = {
        "source": SOURCE,
        "run_date": run_date.isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "keywords": per_keyword,
        "total_rows": sum(k["jobs"] for k in per_keyword.values()),
        "unique_jobs": len(listed),
        "relevant_jobs": len(relevant),
        "details": details,
    }
    common.write_json(out_dir / "_manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    common.setup_logging()
    result = run()
    log.info("Done: %d unique jobs listed, %d new detail pages (run_date=%s)",
             result["unique_jobs"], len(result["details"]["saved"]), result["run_date"])
