-- Singular test: the most recent scraper run of EACH source must look healthy.
--   * it found at least `min_daily_jobs` unique jobs (a sudden drop usually means the
--     site changed its API/HTML, or we got blocked)
--   * optionally (daily pipeline only) it is not older than `max_data_age_days`
-- Thresholds are dbt vars so CI (tiny fixture data) and production can differ:
--   dbt build --vars '{min_daily_jobs: 10, max_data_age_days: 2}'

{% set min_jobs = var('min_daily_jobs', 1) %}
{% set max_age = var('max_data_age_days', none) %}

with latest as (
    select distinct on (source)
        source, dt, (manifest ->> 'unique_jobs')::int as unique_jobs
    from {{ source('raw', 'ingestion_runs') }}
    order by source, dt desc
)

select
    source,
    dt,
    unique_jobs,
    case
        when unique_jobs < {{ min_jobs }} then 'too few jobs: ' || unique_jobs || ' < {{ min_jobs }}'
        {% if max_age is not none %}
        when dt < current_date - {{ max_age }} then 'stale: last run on ' || dt
        {% endif %}
    end as problem
from latest
where unique_jobs < {{ min_jobs }}
{% if max_age is not none %}
   or dt < current_date - {{ max_age }}
{% endif %}
