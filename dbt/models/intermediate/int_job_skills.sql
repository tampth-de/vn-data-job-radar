-- One row per (day, job, canonical skill).
-- Raw skill tags are lower-cased and trimmed, then mapped through the skill_dictionary
-- seed so that aliases count as one skill ("pyspark" -> "spark", "reactjs" -> "react").
-- Unknown skills keep their cleaned name with category 'uncategorized'.

with snapshots as (
    select * from {{ ref('int_job_snapshots_classified') }}
),

tags as (
    select
        s.snapshot_date,
        s.job_id,
        s.is_data_ai_role,
        s.role_family,
        lower(trim(t.skill_raw)) as alias
    from snapshots s
    cross join lateral unnest(s.skills) as t(skill_raw)
    where trim(t.skill_raw) <> ''
)

select distinct
    t.snapshot_date,
    t.job_id,
    t.is_data_ai_role,
    t.role_family,
    coalesce(d.skill, t.alias)                    as skill,
    coalesce(d.skill_category, 'uncategorized')   as skill_category
from tags t
left join {{ ref('skill_dictionary') }} d on d.alias = t.alias
