"""End-to-end test: synthetic raw files -> loader -> dbt -> marts.

Needs a running, EMPTY warehouse, so it only runs when RUN_INTEGRATION=1, e.g. in CI:

    python -m load.topdev --raw-root tests/fixtures/raw
    (cd dbt && dbt build --profiles-dir .)
    RUN_INTEGRATION=1 python -m pytest tests/test_pipeline_integration.py

Fixture story (tests/fixtures/raw/topdev):
    day 1: jobs 1001 (Data Engineer, also matched by "AI"), 1002 (Data Analyst),
           1003 (Telesales noise), 1004 (AI Engineer, USD salary)
    day 2: only 1001 and 1002 are still listed; 1001 raised its salary and changed
           skills (Spark -> PySpark, + Postgres); 1002 only reordered its skills
"""

import os

import pytest

from load.db import connect

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1", reason="needs a warehouse loaded with fixtures"
)


@pytest.fixture(scope="module")
def jobs() -> dict[int, dict]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("select * from marts.fct_job_postings")
            columns = [c.name for c in cur.description]
            return {row[1]: dict(zip(columns, row)) for row in cur.fetchall()}
    finally:
        conn.close()


def query(sql: str) -> list[tuple]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def test_one_row_per_job_despite_duplicate_keywords(jobs):
    assert sorted(jobs) == [1001, 1002, 1003, 1004]


def test_lifecycle(jobs):
    assert jobs[1001]["days_seen"] == 2 and jobs[1001]["is_active"]
    assert jobs[1003]["days_seen"] == 1 and not jobs[1003]["is_active"]  # closed on day 2
    assert str(jobs[1004]["last_seen_date"]) == "2026-01-01"


def test_role_classification(jobs):
    assert jobs[1001]["role_family"] == "data_engineer"
    assert jobs[1002]["role_family"] == "data_analyst"
    assert jobs[1003]["role_family"] == "non_data"
    assert jobs[1003]["is_data_ai_role"] is False
    assert jobs[1004]["role_family"] == "ai_engineer"


def test_masked_salary_ranges_in_vnd(jobs):
    # latest version (day 2): "4******* - 6******* VND"
    assert jobs[1001]["salary_min_low_vnd"] == 40_000_000
    assert jobs[1001]["salary_max_high_vnd"] == 69_999_999
    # USD 2*** - 3*** converted with the fx_rates seed (26,000 VND/USD)
    assert jobs[1004]["salary_min_low_vnd"] == 2_000 * 26_000
    assert jobs[1004]["salary_max_high_vnd"] == 3_999 * 26_000
    # negotiable: no range, but TopDev's own estimate is kept
    assert jobs[1002]["salary_is_negotiable"] is True
    assert jobs[1002]["salary_min_low_vnd"] is None
    assert jobs[1002]["salary_estimate_min_vnd"] == 15_000_000


def test_experience_levels_and_work_mode(jobs):
    assert (jobs[1001]["experience_years_min"], jobs[1001]["experience_years_max"]) == (3, 5)
    assert (jobs[1002]["experience_years_min"], jobs[1002]["experience_years_max"]) == (0, 0)
    assert (jobs[1002]["level_rank_min"], jobs[1002]["level_rank_max"]) == (2, 3)
    assert jobs[1002]["work_mode"] == "remote"
    assert jobs[1001]["primary_province"] == "Thành phố Hồ Chí Minh"


def test_skills_are_normalized():
    skills = {row[0] for row in query("select skill from marts.bridge_job_skills where job_id = 1002")}
    assert skills == {"sql", "power bi", "python"}  # " python " trimmed and lower-cased


def test_skill_aliases_are_merged():
    rows = dict(query("select skill, skill_category from marts.bridge_job_skills where job_id = 1001"))
    assert rows["spark"] == "big_data"          # "PySpark" -> spark
    assert rows["postgresql"] == "database"     # "Postgres" -> postgresql
    assert "pyspark" not in rows


def test_scd2_history():
    versions = query(
        "select job_id, version_number, valid_from::text, valid_to::text, is_current"
        " from marts.dim_job_history order by job_id, version_number"
    )
    by_job = {}
    for job_id, *rest in versions:
        by_job.setdefault(job_id, []).append(tuple(rest))

    # 1001 changed salary/skills on day 2 -> two versions
    assert by_job[1001] == [(1, "2026-01-01", "2026-01-01", False), (2, "2026-01-02", None, True)]
    # 1002 only reordered its skills -> still one version
    assert by_job[1002] == [(1, "2026-01-01", None, True)]
    # 1003 disappeared but never changed -> one current version (closure is tracked in fct)
    assert by_job[1003] == [(1, "2026-01-01", None, True)]


def test_skill_demand_excludes_non_data_jobs():
    rows = dict(query(
        "select skill, jobs_requiring_skill from marts.agg_skill_demand_daily"
        " where snapshot_date = '2026-01-01'"
    ))
    assert "telesales" not in rows   # only came from the non-data job 1003
    assert rows["python"] == 3       # 1001, 1002, 1004
