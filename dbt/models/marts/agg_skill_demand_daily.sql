-- How many active Data/AI postings ask for each skill, per day. Feeds the "trending skills" chart.
-- Only jobs classified as Data/AI roles are counted (sales/marketing noise is excluded).

with relevant as (
    select * from {{ ref('int_job_snapshots_classified') }}
    where is_data_ai_role
),

snapshot_skills as (
    select distinct
        r.snapshot_date,
        r.job_id,
        lower(trim(sk.skill_raw)) as skill
    from relevant r
    cross join lateral unnest(r.skills) as sk(skill_raw)
    where trim(sk.skill_raw) <> ''
),

daily_totals as (
    select snapshot_date, count(distinct job_id) as jobs_that_day
    from relevant
    group by snapshot_date
)

select
    ss.snapshot_date,
    ss.skill,
    count(distinct ss.job_id)                                          as jobs_requiring_skill,
    dt.jobs_that_day,
    round(100.0 * count(distinct ss.job_id) / dt.jobs_that_day, 1)     as pct_of_jobs
from snapshot_skills ss
join daily_totals dt using (snapshot_date)
group by ss.snapshot_date, ss.skill, dt.jobs_that_day
