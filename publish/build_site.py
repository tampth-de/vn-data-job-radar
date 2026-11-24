"""Build the public static site (GitHub Pages) from the warehouse marts.

    python -m publish.build_site --out _site

Only AGGREGATES are published: counts, shares and averages. No job titles, company
names or links leave the warehouse, in line with the job boards' terms (listings
may not be republished) and docs/source_survey.md. Every number is credited to its
sources on the page.

Output: _site/index.html (data embedded, works offline) and _site/data.json (the same
numbers, for transparency).
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from ingestion.common import setup_logging
from load.db import connect

TEMPLATE = Path(__file__).with_name("template.html")
REPO_URL = "https://github.com/tampth-de/vn-data-job-radar"

ACTIVE = "is_active and is_data_ai_role"
LATEST_SKILL_DAY = "(select max(snapshot_date) from marts.agg_skill_demand_daily)"

log = logging.getLogger(__name__)


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def fetch(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    cols = [c.name for c in cur.description]
    return [{k: _plain(v) for k, v in zip(cols, row)} for row in cur.fetchall()]


def collect() -> dict:
    conn = connect()
    try:
        with conn.cursor() as cur:
            headline = fetch(cur, f"""
                select
                    count(distinct posting_key) filter (where {ACTIVE})               as active_postings,
                    count(distinct company_name) filter (where {ACTIVE})              as companies_hiring,
                    count(distinct posting_key) filter (where is_data_ai_role)        as postings_tracked,
                    round(100.0 * count(distinct posting_key) filter (where {ACTIVE})
                          / nullif(count(distinct posting_key) filter (where is_active), 0)) as pct_relevant,
                    count(distinct posting_key) filter (where is_data_ai_role and not is_active) as closed_postings,
                    round(avg(last_seen_date - first_seen_date + 1)
                          filter (where is_data_ai_role and not is_active), 1)        as avg_days_listed_closed
                from marts.fct_job_postings
            """)[0]
            span = fetch(cur, """
                select min(snapshot_date) as first_day, max(snapshot_date) as last_day,
                       count(distinct snapshot_date) as days_tracked
                from intermediate.int_job_snapshots
            """)[0]
            new_7d = fetch(cur, f"""
                with b as (select min(first_seen_date) as d0, max(last_seen_date) as d1 from marts.fct_job_postings)
                select count(distinct posting_key) as n from marts.fct_job_postings, b
                where is_data_ai_role and first_seen_date > greatest(d0, d1 - 7)
            """)[0]["n"]
            sources = fetch(cur, f"""
                select source, count(*) filter (where {ACTIVE}) as active, min(first_seen_date) as since
                from marts.fct_job_postings group by 1 order by since, 1
            """)
            daily = fetch(cur, """
                select snapshot_date as day, source, count(distinct posting_key) as postings
                from intermediate.int_job_snapshots_classified
                where is_data_ai_role group by 1, 2 order by 1, 2
            """)
            daily_total = fetch(cur, """
                select snapshot_date as day, count(distinct posting_key) as postings
                from intermediate.int_job_snapshots_classified
                where is_data_ai_role group by 1 order by 1
            """)
            skills = fetch(cur, f"""
                select skill, skill_category as category, jobs_requiring_skill as postings, pct_of_jobs as pct
                from marts.agg_skill_demand_daily
                where snapshot_date = {LATEST_SKILL_DAY}
                order by postings desc, skill limit 15
            """)
            categories = fetch(cur, f"""
                select skill_category as category, count(distinct posting_key) as postings
                from intermediate.int_job_skills
                where is_data_ai_role and snapshot_date = {LATEST_SKILL_DAY}
                  and skill_category not in ('uncategorized', 'other', 'role_tag')
                group by 1 order by 2 desc
            """)
            roles = fetch(cur, f"""
                select role_family as role, count(distinct posting_key) as postings
                from marts.fct_job_postings where {ACTIVE} group by 1 order by 2 desc
            """)
            salary = fetch(cur, f"""
                select role_family as role,
                       count(distinct posting_key) filter (where salary_max_high_vnd is not null) as with_salary,
                       round(avg(salary_min_low_vnd) / 1e6, 1)  as avg_min_m,
                       round(avg(salary_max_high_vnd) / 1e6, 1) as avg_max_m
                from marts.fct_job_postings
                where {ACTIVE}
                group by 1
                having count(*) filter (where salary_max_high_vnd is not null) > 0
                order by avg_max_m desc nulls last
            """)
            provinces = fetch(cur, f"""
                select p as province, count(distinct posting_key) as postings
                from marts.fct_job_postings f cross join lateral unnest(f.provinces) as p
                where {ACTIVE} group by 1 order by 2 desc limit 8
            """)
            work_mode = fetch(cur, f"""
                select coalesce(work_mode, 'not stated') as work_mode, count(distinct posting_key) as postings
                from marts.fct_job_postings where {ACTIVE} group by 1 order by 2 desc
            """)
            experience = fetch(cur, f"""
                select case
                         when experience_years_min is null then 'Not stated'
                         when experience_years_min = 0 then 'None'
                         when experience_years_min <= 2 then '1–2 years'
                         when experience_years_min <= 4 then '3–4 years'
                         else '5+ years'
                       end as experience,
                       min(coalesce(experience_years_min, 99)) as sort_key,
                       count(distinct posting_key) as postings
                from marts.fct_job_postings where {ACTIVE}
                group by 1 order by 2
            """)
    finally:
        conn.close()

    headline["new_last_7_days"] = new_7d
    for row in experience:
        row.pop("sort_key", None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "repo_url": REPO_URL,
        "span": span,
        "headline": headline,
        "sources": sources,
        "daily": daily,
        "daily_total": daily_total,
        "skills": skills,
        "skill_categories": categories,
        "roles": roles,
        "salary": salary,
        "provinces": provinces,
        "work_mode": work_mode,
        "experience": experience,
    }


def render(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # safe inside <script>
    return TEMPLATE.read_text(encoding="utf-8").replace("__DATA_JSON__", payload)


def build(out_dir: Path) -> Path:
    data = collect()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(render(data), encoding="utf-8")
    (out_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    log.info("site built in %s: %d active Data/AI postings, %d days tracked",
             out_dir, data["headline"]["active_postings"], data["span"]["days_tracked"])
    return out_dir / "index.html"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("_site"))
    args = parser.parse_args()
    setup_logging()
    build(args.out)
