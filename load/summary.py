"""Print a Markdown summary of the latest day in the marts (aggregates only).

In GitHub Actions it is appended to the run page:
    python -m load.summary >> "$GITHUB_STEP_SUMMARY"
"""

from load.db import connect

LATEST = "(select max(snapshot_date) from marts.agg_skill_demand_daily)"


def fetch(cur, sql: str) -> list[tuple]:
    cur.execute(sql)
    return cur.fetchall()


def build_summary() -> str:
    conn = connect()
    try:
        with conn.cursor() as cur:
            (latest_date,) = fetch(cur, f"select {LATEST}")[0]
            totals = fetch(cur, """
                select count(*) filter (where is_active),
                       count(*) filter (where is_active and is_data_ai_role),
                       count(*) filter (where is_data_ai_role)
                from marts.fct_job_postings
            """)[0]
            roles = fetch(cur, """
                select role_family, count(*) from marts.fct_job_postings
                where is_active and is_data_ai_role group by 1 order by 2 desc
            """)
            skills = fetch(cur, f"""
                select skill, jobs_requiring_skill, pct_of_jobs from marts.agg_skill_demand_daily
                where snapshot_date = {LATEST} order by 2 desc, 1 limit 10
            """)
    finally:
        conn.close()

    active, active_data_ai, all_time_data_ai = totals
    lines = [
        f"## Job radar — {latest_date}",
        "",
        f"- Active postings found: **{active}**, of which Data/AI roles: **{active_data_ai}**",
        f"- Data/AI postings seen since tracking started: **{all_time_data_ai}**",
        "",
        "| Role family | Active jobs |",
        "|---|---|",
        *[f"| {role} | {n} |" for role, n in roles],
        "",
        "| Top skills (Data/AI jobs) | Jobs | Share |",
        "|---|---|---|",
        *[f"| {skill} | {n} | {pct}% |" for skill, n, pct in skills],
        "",
        "_Source: topdev.vn public job listings, aggregated._",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(build_summary())
