-- How many active Data/AI postings (all sources) ask for each canonical skill, per day.
-- Feeds the "trending skills" chart. Sales/marketing noise is excluded.

with skills as (
    select * from {{ ref('int_job_skills') }}
    where is_data_ai_role
),

daily_totals as (
    select snapshot_date, count(distinct job_key) as jobs_that_day
    from {{ ref('int_job_snapshots_classified') }}
    where is_data_ai_role
    group by snapshot_date
)

select
    s.snapshot_date,
    s.skill,
    s.skill_category,
    count(distinct s.job_key)                                      as jobs_requiring_skill,
    dt.jobs_that_day,
    round(100.0 * count(distinct s.job_key) / dt.jobs_that_day, 1) as pct_of_jobs
from skills s
join daily_totals dt using (snapshot_date)
group by s.snapshot_date, s.skill, s.skill_category, dt.jobs_that_day
