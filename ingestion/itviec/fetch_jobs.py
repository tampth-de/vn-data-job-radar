"""Fetch Data/AI job search pages from ITviec and save the raw HTML.

Output layout (one folder per run date, replaced on re-run -> idempotent):

    data/raw/itviec/dt=YYYY-MM-DD/
        category=data-engineer/page_001.html
        category=ai/page_001.html
        ...
        _manifest.json

HTML is stored as-is (bronze layer). The parser in parse.py is only used here to
count jobs and decide when to stop paging; the real parsing happens in staging.
"""

import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from ingestion import common
from ingestion.itviec.parse import parse_job_cards, parse_total

SOURCE = "itviec"
BASE_URL = "https://itviec.com/it-jobs/{category}"
JOBS_PER_PAGE = 20
MAX_PAGES = 20  # safety net in case the page count is misread

# ITviec category slugs related to Data/AI. Broad skills like "python" or "sql"
# are left out on purpose: they are dominated by general software jobs.
CATEGORIES = [
    "data-engineer",
    "data-analyst",
    "data-science",
    "ai",
    "machine-learning",
    "big-data",
    "business-intelligence",
]

log = logging.getLogger(__name__)


def fetch_page(client: httpx.Client, category: str, page: int) -> str:
    params = {"page": page} if page > 1 else None
    return common.get_with_retries(client, BASE_URL.format(category=category), params=params).text


def fetch_category(client: httpx.Client, category: str) -> list[str]:
    """Fetch every result page of one category. Returns the raw HTML pages."""
    pages = []
    page = 1
    last_page = 1
    while page <= MAX_PAGES:
        html = fetch_page(client, category, page)
        n_cards = len(parse_job_cards(html))
        if page == 1:
            total = parse_total(html)
            last_page = max(1, math.ceil(total / JOBS_PER_PAGE)) if total else 1
        if n_cards == 0:  # past the last page, or the layout changed
            if page == 1:
                pages.append(html)  # keep it: an empty first page is worth investigating
            break
        pages.append(html)
        log.info("category=%s page %d/%d: %d jobs", category, page, last_page, n_cards)
        if page >= last_page:
            break
        page += 1
        common.polite_pause()
    return pages


def run(run_date: date | None = None, raw_root: Path | None = None) -> dict:
    run_date = run_date or date.today()
    started_at = datetime.now(timezone.utc)
    per_category = {}
    unique_slugs = set()

    with common.Partition(SOURCE, run_date, raw_root) as part, common.make_client() as client:
        for i, category in enumerate(CATEGORIES):
            if i > 0:
                common.polite_pause()
            pages = fetch_category(client, category)
            n_jobs = 0
            for page_no, html in enumerate(pages, start=1):
                common.write_text(part.path / f"category={category}" / f"page_{page_no:03d}.html", html)
                jobs = parse_job_cards(html)
                n_jobs += len(jobs)
                unique_slugs.update(job["job_slug"] for job in jobs if job["job_slug"])
            per_category[category] = {"pages": len(pages), "jobs": n_jobs}

        if not unique_slugs:
            raise common.SourceUnavailable("ITviec pages contained no jobs; keeping the previous partition")

        manifest = {
            "source": SOURCE,
            "run_date": run_date.isoformat(),
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "categories": per_category,
            "total_rows": sum(c["jobs"] for c in per_category.values()),
            "unique_jobs": len(unique_slugs),
        }
        common.write_json(part.path / "_manifest.json", manifest)
        part.commit()
    return manifest


if __name__ == "__main__":
    common.setup_logging()
    result = run()
    log.info("Done: %d rows, %d unique jobs (run_date=%s)",
             result["total_rows"], result["unique_jobs"], result["run_date"])
