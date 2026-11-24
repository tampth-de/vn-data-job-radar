-- One row per (job, canonical skill), using each job's most recent snapshot.

select
    s.source,
    s.job_key,
    s.skill,
    s.skill_category
from {{ ref('int_job_skills') }} s
join {{ ref('fct_job_postings') }} f
  on f.job_key = s.job_key
 and f.last_seen_date = s.snapshot_date
