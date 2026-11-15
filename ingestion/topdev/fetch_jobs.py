"""Fetch job postings from the TopDev public API and save the raw JSON responses."""

import json
from datetime import date
from pathlib import Path

import httpx

API_URL = "https://api.topdev.vn/td/v2/jobs"
HEADERS = {"User-Agent": "vn-data-job-radar/0.1 (portfolio project)"}
RAW_DIR = Path("data/raw/topdev")


def fetch_page(keyword: str, page: int) -> dict:
    """Call the API for one page of results and return the parsed JSON."""
    params = {
        "keyword": keyword,
        "page": page,
        "page_size": 20,
        "locale": "vi_VN",
        "fields[job]": "id,title,salary,skills_arr,addresses,job_levels_str,"
                       "experiences_str,job_types_str,published,refreshed,detail_url",
        "fields[company]": "display_name,industries_str",
    }
    response = httpx.get(API_URL, params=params, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.json()


def save_raw(data: dict, page: int) -> Path:
    """Save one API response as-is to data/raw/topdev/dt=YYYY-MM-DD/page_NNN.json."""
    out_dir = RAW_DIR / f"dt={date.today().isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    file_path = out_dir / f"page_{page:03d}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return file_path


if __name__ == "__main__":
    data = fetch_page("data engineer", page=1)
    path = save_raw(data, page=1)
    print(f"Saved {len(data['data'])} jobs -> {path}")
