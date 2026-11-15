"""Fetch Data/AI job postings from the TopDev public API and save the raw JSON responses.

Output layout (one folder per run date, overwritten on re-run -> idempotent):

    data/raw/topdev/dt=YYYY-MM-DD/
        keyword=data/page_001.json
        keyword=AI/page_001.json
        ...
        _manifest.json      # run metadata: time, keywords, counts

Raw files are stored exactly as returned by the API. Cleaning and deduplication
happen later in the staging layer, so we can always reprocess from raw.
"""

import json
import logging
import shutil
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

API_URL = "https://api.topdev.vn/td/v2/jobs"
HEADERS = {"User-Agent": "vn-data-job-radar/0.1 (portfolio project)"}
RAW_DIR = Path("data/raw/topdev")

# TopDev search matches mostly on job titles. "analyst" is excluded on purpose:
# it matches ~9k unrelated jobs. Relevance filtering happens in staging.
KEYWORDS = ["data", "AI", "dữ liệu", "analytics", "big data", "BI"]

PAGE_SIZE = 50
SLEEP_BETWEEN_REQUESTS = 2.0  # seconds, be polite to the server
MAX_RETRIES = 3
JOB_FIELDS = (
    "id,title,salary,skills_arr,addresses,job_levels_str,experiences_str,"
    "job_types_str,published,refreshed,detail_url"
)
COMPANY_FIELDS = "display_name,industries_str"

log = logging.getLogger(__name__)


def fetch_page(client: httpx.Client, keyword: str, page: int) -> dict:
    """Fetch one page of results, retrying on network errors and 5xx/429."""
    params = {
        "keyword": keyword,
        "page": page,
        "page_size": PAGE_SIZE,
        "locale": "vi_VN",
        "fields[job]": JOB_FIELDS,
        "fields[company]": COMPANY_FIELDS,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.get(API_URL, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TransportError) or (
                exc.response.status_code == 429 or exc.response.status_code >= 500
            )
            if not retryable or attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt  # 2s, 4s, ...
            log.warning("keyword=%r page=%d failed (%s), retry in %ds", keyword, page, exc, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


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
        time.sleep(SLEEP_BETWEEN_REQUESTS)


def save_page(out_dir: Path, keyword: str, page: int, data: dict) -> Path:
    """Write one raw API response to <out_dir>/keyword=<kw>/page_NNN.json."""
    kw_dir = out_dir / f"keyword={keyword}"
    kw_dir.mkdir(parents=True, exist_ok=True)
    file_path = kw_dir / f"page_{page:03d}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return file_path


def run(run_date: date | None = None) -> dict:
    """Fetch all keywords and write one dated partition. Returns the run manifest."""
    run_date = run_date or date.today()
    out_dir = RAW_DIR / f"dt={run_date.isoformat()}"

    # Idempotency: replace the whole partition, so a re-run never leaves stale files.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    started_at = datetime.now(timezone.utc)
    per_keyword = {}
    unique_ids = set()

    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for i, keyword in enumerate(KEYWORDS):
            if i > 0:
                time.sleep(SLEEP_BETWEEN_REQUESTS)
            pages = fetch_keyword(client, keyword)
            n_jobs = 0
            for page_no, data in enumerate(pages, start=1):
                save_page(out_dir, keyword, page_no, data)
                jobs = data.get("data", [])
                n_jobs += len(jobs)
                unique_ids.update(job["id"] for job in jobs)
            per_keyword[keyword] = {"pages": len(pages), "jobs": n_jobs}

    manifest = {
        "source": "topdev",
        "run_date": run_date.isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "keywords": per_keyword,
        "total_rows": sum(k["jobs"] for k in per_keyword.values()),
        "unique_jobs": len(unique_ids),
    }
    with open(out_dir / "_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # hide per-request URL noise
    result = run()
    log.info(
        "Done: %d rows, %d unique jobs -> %s",
        result["total_rows"], result["unique_jobs"], RAW_DIR / f"dt={result['run_date']}",
    )
