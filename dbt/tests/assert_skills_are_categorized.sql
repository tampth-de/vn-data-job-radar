-- Warning-level test: lists skills seen in Data/AI jobs that are missing from the
-- skill_dictionary seed. It never breaks the pipeline; it tells us which aliases
-- to add next (`dbt build` shows it as WARN).
{{ config(severity='warn') }}

select skill, count(distinct job_key) as jobs
from {{ ref('int_job_skills') }}
where skill_category = 'uncategorized'
  and is_data_ai_role
group by skill
