-- One row per job posting ever seen (all sources), with its lifecycle and latest attributes.
--   first_seen_date / last_seen_date : from the daily snapshots
--   is_active                        : seen in its source's most recent run (per source, so a
--                                      failed run of one site does not "close" all its jobs)
-- Salaries are converted to VND per month with fixed rates from the fx_rates seed.

with snapshots as (
    select * from {{ ref('int_job_snapshots_classified') }}
),

lifecycle as (
    select
        job_key,
        min(snapshot_date)            as first_seen_date,
        max(snapshot_date)            as last_seen_date,
        count(distinct snapshot_date) as days_seen
    from snapshots
    group by job_key
),

latest_run_per_source as (
    select source, max(snapshot_date) as max_date
    from snapshots
    group by source
),

latest as (
    select distinct on (job_key) *
    from snapshots
    order by job_key, snapshot_date desc
),

levels as (
    -- a job can list several levels ("Chuyên viên, Chuyên viên cấp cao"): keep the range
    select
        l.job_key,
        min(m.level_rank) filter (where m.level_rank > 0) as level_rank_min,
        max(m.level_rank) filter (where m.level_rank > 0) as level_rank_max,
        array_agg(distinct m.level_en) filter (where m.level_en is not null) as levels_en
    from latest l
    cross join lateral unnest(l.levels_vi) as lv(level_vi)
    left join {{ ref('topdev_level_map') }} m on m.level_vi = lv.level_vi
    group by l.job_key
)

select
    l.source,
    l.job_key,
    l.job_id,
    l.title,
    l.role_family,
    l.is_data_ai_role,
    l.category_name,
    l.company_id,
    l.company_name,
    l.job_url,
    l.provinces,
    l.provinces[1]                                 as primary_province,
    l.work_mode,
    l.skills,
    l.levels_vi,
    lv.levels_en,
    lv.level_rank_min,
    lv.level_rank_max,
    l.experience_years_min,
    l.experience_years_max,
    l.salary_is_negotiable,
    l.salary_is_masked,
    l.salary_currency,
    l.salary_text,
    round(l.salary_min_low  * fx.vnd_per_unit)     as salary_min_low_vnd,
    round(l.salary_max_high * fx.vnd_per_unit)     as salary_max_high_vnd,
    round(l.salary_estimate_min * fx.vnd_per_unit) as salary_estimate_min_vnd,
    round(l.salary_estimate_max * fx.vnd_per_unit) as salary_estimate_max_vnd,
    l.published_date,
    l.refreshed_date,
    l.valid_through_date,
    lc.first_seen_date,
    lc.last_seen_date,
    lc.days_seen,
    lc.last_seen_date = lr.max_date                as is_active,
    l.has_details,
    l.matched_keywords
from latest l
join lifecycle lc using (job_key)
join latest_run_per_source lr using (source)
left join levels lv using (job_key)
left join {{ ref('fx_rates') }} fx on fx.currency = l.salary_currency
