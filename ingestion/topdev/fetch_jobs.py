"""Fetch Data/AI job postings from the TopDev public API and save the raw JSON responses.

Output layout (one folder per run date, replaced on re-run -> idempotent):

    data/raw/topdev/dt=YYYY-MM-DD/
        keyword=data/page_001.json
        keyword=AI/page_001.json
        ...
        _manifest.json      # run metadata: time, keywords, counts

Raw files are stored exactly as returned by the API. Cleaning and deduplication
happen later in the staging layer, so we can always reprocess from raw.
"""

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from ingestion import common

SOURCE = "topdev"
API_URL = "https://api.topdev.vn/td/v2/jobs"

# TopDev search matches mostly on job titles. "analyst" is excluded on purpose:
# it matches ~9k unrelated jobs. Relevance filtering happens in staging.
KEYWORDS = ["data", "AI", "dữ liệu", "analytics", "big data", "BI"]

PAGE_SIZE = 50
# "company" must be listed here, otherwise the API omits the nested company object.
JOB_FIELDS = (
    "id,title,company,salary,skills_arr,addresses,job_levels_str,experiences_str,"
    "job_types_str,published,refreshed,detail_url"
)
COMPANY_FIELDS = "display_name,slug,industries_str"

log = logging.getLogger(__name__)


def fetch_page(client: httpx.Client, keyword: str, page: int) -> dict:
    """Fetch one page of API results as parsed JSON."""
    params = {
        "keyword": keyword,
        "page": page,
        "page_size": PAGE_SIZE,
        "locale": "vi_VN",
        "fields[job]": JOB_FIELDS,
        "fields[company]": COMPANY_FIELDS,
    }
    return common.get_with_retries(client, API_URL, params=params).json()


def fetch_keyword(client: httpx.Client, keyword: str) -> list[dict]:
    """Fetch every page for one keyword, following meta.last_page."""
    pages = []
    page = 1
    while True:
        data = fetch_page(client, keyword, page)
        pages.append(data)
        last_page = data.get("meta", {}).get("last_page") or 1
        log.info("keyword=%r page %d/%d: %d jobs", keyword, page, last_page, len(data.get("data", [])))
        if page >= last_page or not data.get("data"):
            return pages
        page += 1
        common.polite_pause()


def run(run_date: date | None = None, raw_root: Path | None = None) -> dict:
    """Fetch all keywords and write one dated partition. Returns the run manifest."""
    run_date = run_date or date.today()
    out_dir = common.reset_partition(SOURCE, run_date, raw_root)
    started_at = datetime.now(timezone.utc)
    per_keyword = {}
    unique_ids = set()

    with common.make_client() as client:
        for i, keyword in enumerate(KEYWORDS):
            if i > 0:
                common.polite_pause()
            pages = fetch_keyword(client, keyword)
            n_jobs = 0
            for page_no, data in enumerate(pages, start=1):
                common.write_json(out_dir / f"keyword={keyword}" / f"page_{page_no:03d}.json", data)
                jobs = data.get("data", [])
                n_jobs += len(jobs)
                unique_ids.update(job["id"] for job in jobs)
            per_keyword[keyword] = {"pages": len(pages), "jobs": n_jobs}

    manifest = {
        "source": SOURCE,
        "run_date": run_date.isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "keywords": per_keyword,
        "total_rows": sum(k["jobs"] for k in per_keyword.values()),
        "unique_jobs": len(unique_ids),
    }
    common.write_json(out_dir / "_manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    common.setup_logging()
    result = run()
    log.info("Done: %d rows, %d unique jobs (run_date=%s)",
             result["total_rows"], result["unique_jobs"], result["run_date"])
