-- One row per (job, skill). Skill names are normalized to lower case so that
-- "Python", "python " and "PYTHON" count as the same skill.

select distinct
    f.source,
    f.job_id,
    lower(trim(s.skill_raw)) as skill
from {{ ref('fct_job_postings') }} f
cross join lateral unnest(f.skills) as s(skill_raw)
where trim(s.skill_raw) <> ''
