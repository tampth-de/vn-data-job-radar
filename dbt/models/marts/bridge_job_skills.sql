-- One row per (job, canonical skill), using each job's most recent snapshot.

select
    'topdev' as source,
    s.job_id,
    s.skill,
    s.skill_category
from {{ ref('int_job_skills') }} s
join {{ ref('fct_job_postings') }} f
  on f.job_id = s.job_id
 and f.last_seen_date = s.snapshot_date
