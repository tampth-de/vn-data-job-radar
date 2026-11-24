"""Parse CareerLink pages.

- Search result pages: job links look like /tim-viec-lam/<slug>/<numeric id>.
- Job pages embed a schema.org `JobPosting` as JSON-LD (the machine-readable data
  job boards publish for search engines): title, company, dates, salary, location,
  months of experience, description.
"""

import json
import re

from bs4 import BeautifulSoup

JOB_LINK_RE = re.compile(r"^/tim-viec-lam/[^/?#]+/(\d+)$")
TOTAL_RE = re.compile(r"([\d.,]+)\s*việc làm", re.IGNORECASE)
NEW_BADGE_RE = re.compile(r"^(Mới|New)\s+", re.IGNORECASE)

# Cheap pre-filter on search-result titles, used to decide which job pages are worth
# requesting. Deliberately loose: the dbt classifier makes the final call.
RELEVANT_TITLE_RE = re.compile(
    r"data|dữ liệu|dự liệu|\bai\b|a\.i\.|trí tuệ nhân tạo|machine learning|\bml\b|deep learning"
    r"|analyst|analytics|phân tích|\bbi\b|business intelligence|power bi|scientist|insight"
    r"|database|\bdba\b|\bllm\b|\bnlp\b|computer vision|\betl\b",
    re.IGNORECASE,
)


def clean_title(text: str) -> str:
    return NEW_BADGE_RE.sub("", " ".join(text.split()))


def looks_relevant(title: str) -> bool:
    return bool(RELEVANT_TITLE_RE.search(title))


def parse_job_links(html: str) -> dict[int, tuple[str, str]]:
    """Return {job_id: (path, title)} for every job linked from a search result page."""
    soup = BeautifulSoup(html, "html.parser")
    jobs: dict[int, tuple[str, str]] = {}
    for a in soup.find_all("a", href=True):
        match = JOB_LINK_RE.match(a["href"])
        if not match:
            continue
        job_id = int(match.group(1))
        title = clean_title(a.get_text(" "))
        # the same job is often linked twice (logo + title): keep the link with text
        if job_id not in jobs or (title and not jobs[job_id][1]):
            jobs[job_id] = (a["href"], title)
    return jobs


def parse_total(html: str) -> int | None:
    """Total number of results, e.g. '9 việc làm'."""
    match = TOTAL_RE.search(BeautifulSoup(html, "html.parser").get_text(" "))
    return int(re.sub(r"[.,]", "", match.group(1))) if match else None


def _iter_jsonld_objects(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_objects(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_jsonld_objects(data["@graph"])


def extract_job_posting(html: str) -> dict | None:
    """Return the JSON-LD JobPosting object of a job page, or None if absent."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.get_text())
        except json.JSONDecodeError:
            continue
        for obj in _iter_jsonld_objects(data):
            if obj.get("@type") == "JobPosting":
                return obj
    return None
