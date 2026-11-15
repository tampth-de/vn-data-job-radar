"""Parse ITviec search result pages (HTML) into plain job dictionaries.

Used by the ingestion step for counting/validation, and later by the staging layer.
Salary is hidden for anonymous visitors ("Sign in to view salary"), so it is
returned as None in that case. We never log in to scrape.
"""

import re

from bs4 import BeautifulSoup, Tag

SALARY_HIDDEN = "sign in to view salary"


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    text = " ".join(node.get_text().split())
    return text or None


def parse_total(html: str) -> int | None:
    """Read the total job count from the page heading, e.g. '25 data engineer jobs in Vietnam'."""
    h1 = BeautifulSoup(html, "html.parser").find("h1")
    match = re.match(r"\s*([\d,.]+)", h1.get_text()) if h1 else None
    return int(re.sub(r"[,.]", "", match.group(1))) if match else None


def parse_job_card(card: Tag) -> dict:
    title_link = card.select_one("h3 a")
    company_link = card.select_one("span.ims-2 a")
    logo_link = card.select_one("a.logo-employer-card")
    posted = _text(card.select_one("span.small-text.text-dark-grey"))
    salary = _text(card.select_one("div.salary"))
    slug = card.get("data-search--job-selection-job-slug-value")
    company_href = company_link.get("href", "") if company_link else ""

    return {
        "job_slug": slug,
        "job_key": card.get("data-job-key"),
        "title": _text(title_link),
        "url": f"https://itviec.com/it-jobs/{slug}" if slug else None,
        "company_name": _text(company_link),
        "company_legal_name": logo_link.get("title") if logo_link else None,
        "company_slug": company_href.split("/companies/")[-1].split("?")[0] or None,
        "posted_text": posted.removeprefix("Posted").strip() if posted else None,
        "salary_text": None if salary is None or salary.lower() == SALARY_HIDDEN else salary,
        "work_mode": _text(card.select_one("div.text-rich-grey.flex-shrink-0")),
        "location": (card.select_one("div.text-truncate[title]") or {}).get("title"),
        "categories": [_text(a) for a in card.select("a.text-decoration-dot-underline")],
        "skills": [_text(a) for a in card.select("a.itag")],
        "labels": [_text(d) for d in card.select("div.ilabel")],
    }


def parse_job_cards(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    return [parse_job_card(card) for card in soup.select("div.job-card")]
