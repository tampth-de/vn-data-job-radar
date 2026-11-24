"""Dashboard definition as code: every card's SQL, chart type and position.

Grid is 24 columns wide. Queries only read the dbt marts / intermediate models.
"""

LATEST_DAY = "(select max(snapshot_date) from marts.agg_skill_demand_daily)"


def chart(dimensions: list[str], metrics: list[str], **extra) -> dict:
    return {"graph.dimensions": dimensions, "graph.metrics": metrics, **extra}


def pie(dimension: str, metric: str) -> dict:
    return {"pie.dimension": dimension, "pie.metric": metric}


# (name, description, sql, display, visualization_settings, (row, col, width, height))
CARDS = [
    # --- headline numbers -------------------------------------------------------
    ("Active Data/AI jobs", "Data/AI postings listed in the latest run of each source. An ad posted on several boards counts once.",
     "select count(distinct posting_key) as jobs from marts.fct_job_postings where is_active and is_data_ai_role",
     "scalar", {}, (0, 0, 6, 3)),

    ("New Data/AI jobs (last 7 days)",
     "First seen in the last 7 days. The first tracking day is excluded (backlog, not new).",
     """
     with bounds as (
         select min(first_seen_date) as first_day, max(last_seen_date) as last_day
         from marts.fct_job_postings
     )
     select count(distinct posting_key) as jobs
     from marts.fct_job_postings, bounds
     where is_data_ai_role
       and first_seen_date > greatest(first_day, last_day - 7)
     """,
     "scalar", {}, (0, 6, 6, 3)),

    ("Companies hiring Data/AI", "Distinct companies with at least one active Data/AI posting.",
     "select count(distinct company_name) as companies from marts.fct_job_postings"
     " where is_active and is_data_ai_role",
     "scalar", {}, (0, 12, 6, 3)),

    ("% of search results that are real Data/AI jobs",
     "Keyword search returns lots of noise (e.g. 'Telesales - data có sẵn'). Share kept by the classifier.",
     "select round(100.0 * count(distinct posting_key) filter (where is_data_ai_role) / nullif(count(distinct posting_key), 0)) as pct"
     " from marts.fct_job_postings where is_active",
     "scalar", {"scalar.suffix": "%"}, (0, 18, 6, 3)),

    # --- what is in demand ------------------------------------------------------
    ("Top 15 skills in Data/AI jobs (latest day)", "Canonical skills (aliases merged).",
     f"""
     select skill, jobs_requiring_skill as jobs
     from marts.agg_skill_demand_daily
     where snapshot_date = {LATEST_DAY}
     order by jobs desc, skill
     limit 15
     """,
     "row", chart(["skill"], ["jobs"]), (3, 0, 12, 8)),

    ("Active jobs by role family", "Role family assigned from job titles (role_rules seed).",
     """
     select role_family, count(distinct posting_key) as jobs
     from marts.fct_job_postings
     where is_active and is_data_ai_role
     group by 1 order by 2 desc
     """,
     "bar", chart(["role_family"], ["jobs"]), (3, 12, 12, 8)),

    ("Daily Data/AI jobs by role family", "One point per scraping day; fills in as data accumulates.",
     """
     select snapshot_date, role_family, count(distinct posting_key) as jobs
     from intermediate.int_job_snapshots_classified
     where is_data_ai_role
     group by 1, 2 order by 1, 2
     """,
     "line", chart(["snapshot_date", "role_family"], ["jobs"]), (11, 0, 12, 6)),

    ("Skill categories (latest day)", "Number of Data/AI jobs asking for at least one skill of each category.",
     f"""
     select skill_category, count(distinct posting_key) as jobs
     from intermediate.int_job_skills
     where is_data_ai_role and snapshot_date = {LATEST_DAY}
     group by 1 order by 2 desc
     """,
     "pie", pie("skill_category", "jobs"), (11, 12, 12, 6)),

    # --- money, place, seniority --------------------------------------------------
    ("Salary range by role (million VND / month)",
     "CareerLink shows exact salaries; TopDev masks them ('1*******' = 10-19.99M), so for TopDev these "
     "are bounds (lowest possible minimum, highest possible maximum). Negotiable salaries are excluded.",
     """
     select
         role_family,
         count(distinct posting_key) filter (where salary_max_high_vnd is not null) as jobs_with_salary,
         round(avg(salary_min_low_vnd) / 1e6, 1)  as avg_min_low_m,
         round(avg(salary_max_high_vnd) / 1e6, 1) as avg_max_high_m
     from marts.fct_job_postings
     where is_active and is_data_ai_role
     group by 1 order by avg_max_high_m desc nulls last
     """,
     "table", {}, (17, 0, 12, 6)),

    ("Active Data/AI jobs by province", "A job listing several provinces counts in each.",
     """
     select p as province, count(distinct posting_key) as jobs
     from marts.fct_job_postings f
     cross join lateral unnest(f.provinces) as p
     where is_active and is_data_ai_role
     group by 1 order by 2 desc
     """,
     "bar", chart(["province"], ["jobs"]), (17, 12, 12, 6)),

    ("Seniority levels (TopDev only)",
     "Our English mapping of TopDev's Vietnamese levels (topdev_level_map seed). CareerLink has no level field.",
     """
     select m.level_rank, m.level_en as level, count(distinct posting_key) as jobs
     from marts.fct_job_postings f
     cross join lateral unnest(f.levels_vi) as lv(level_vi)
     join reference.topdev_level_map m on m.level_vi = lv.level_vi
     where f.is_active and f.is_data_ai_role
     group by 1, 2 order by 1
     """,
     "bar", chart(["level"], ["jobs"]), (23, 0, 8, 6)),

    ("Work mode", None,
     """
     select work_mode, count(distinct posting_key) as jobs
     from marts.fct_job_postings
     where is_active and is_data_ai_role
     group by 1 order by 2 desc
     """,
     "pie", pie("work_mode", "jobs"), (23, 8, 8, 6)),

    ("Experience required", "Minimum years of experience asked.",
     """
     select
         case
             when experience_years_min is null then '5. not stated'
             when experience_years_min = 0 then '1. none'
             when experience_years_min <= 2 then '2. 1-2 years'
             when experience_years_min <= 4 then '3. 3-4 years'
             else '4. 5+ years'
         end as experience,
         count(distinct posting_key) as jobs
     from marts.fct_job_postings
     where is_active and is_data_ai_role
     group by 1 order by 1
     """,
     "bar", chart(["experience"], ["jobs"]), (23, 16, 8, 6)),

    # --- details & history -------------------------------------------------------
    ("Latest Data/AI postings", None,
     """
     select first_seen_date, source, title, company_name, role_family, salary_text,
            primary_province as province, job_url
     from marts.fct_job_postings
     where is_active and is_data_ai_role
     order by first_seen_date desc, job_key desc
     limit 50
     """,
     "table", {}, (29, 0, 24, 8)),

    ("Postings that changed (SCD2 history)",
     "Every version of postings whose salary, title, levels, skills or location changed.",
     """
     select h.source, h.job_id, h.version_number, h.valid_from, h.valid_to, h.title, h.salary_text, h.levels_vi
     from marts.dim_job_history h
     where h.job_key in (select job_key from marts.dim_job_history where version_number > 1)
     order by h.job_key, h.version_number
     """,
     "table", {}, (37, 0, 12, 6)),

    ("Closed postings: how long were they listed?",
     "Days between first and last time seen. Jobs already open before tracking started make this a lower bound.",
     """
     select role_family,
            count(distinct posting_key) as closed_jobs,
            round(avg(last_seen_date - first_seen_date + 1), 1) as avg_days_listed
     from marts.fct_job_postings
     where not is_active and is_data_ai_role
     group by 1 order by 2 desc
     """,
     "table", {}, (37, 12, 12, 6)),

    # --- sources -------------------------------------------------------------------
    ("Active Data/AI jobs by source",
     "TopDev (public API) and CareerLink (schema.org JobPosting). The same job posted on both counts twice.",
     """
     select source, role_family, count(distinct posting_key) as jobs
     from marts.fct_job_postings
     where is_active and is_data_ai_role
     group by 1, 2 order by 1, 3 desc
     """,
     "bar", chart(["source", "role_family"], ["jobs"], **{"stackable.stack_type": "stacked"}), (43, 0, 12, 6)),

    ("Daily active Data/AI jobs by source", "CareerLink tracking started on 2026-11-24.",
     """
     select snapshot_date, source, count(distinct job_key) as jobs
     from intermediate.int_job_snapshots_classified
     where is_data_ai_role
     group by 1, 2 order by 1, 2
     """,
     "line", chart(["snapshot_date", "source"], ["jobs"]), (43, 12, 12, 6)),
]
