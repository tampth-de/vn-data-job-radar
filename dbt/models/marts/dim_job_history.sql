-- Slowly Changing Dimension type 2: one row per VERSION of a job posting.
-- A new version starts whenever a tracked attribute changes (title, salary, levels,
-- skills, location, ...). valid_to is null for the current version.
--
-- Built from the daily snapshots with a gaps-and-islands pattern instead of
-- `dbt snapshot`: bronze keeps every day, so history is deterministic and can be
-- rebuilt from scratch (as CI and the daily run do).
--
-- Note: CareerLink job pages are fetched once per job, so its versions only change
-- through the search listing; days before a job's page was fetched are skipped so that
-- "details arrived" is not mistaken for a change.

with snapshots as (
    select
        source,
        job_key,
        job_id,
        snapshot_date,
        title,
        company_name,
        salary_text,
        salary_currency,
        salary_is_negotiable,
        levels_vi,
        experience_text,
        work_mode,
        provinces,
        skills,
        md5(concat_ws('||',
            title,
            company_name,
            salary_text,
            salary_currency,
            salary_is_negotiable::text,
            levels_vi::text,
            experience_text,
            work_mode,
            provinces::text,
            (select array_agg(x order by x) from unnest(skills) as x)::text  -- order-insensitive
        )) as attributes_hash
    from {{ ref('int_job_snapshots_classified') }}
    where has_details
),

flagged as (
    select
        *,
        case
            when lag(attributes_hash) over (partition by job_key order by snapshot_date) = attributes_hash
            then 0 else 1
        end as is_new_version
    from snapshots
),

numbered as (
    select
        *,
        sum(is_new_version) over (partition by job_key order by snapshot_date) as version_number
    from flagged
),

versions as (
    select
        source,
        job_key,
        job_id,
        version_number,
        min(snapshot_date) as valid_from,
        max(snapshot_date) as last_seen_in_version,
        -- attributes are identical within a version, take them from the first day
        (array_agg(title           order by snapshot_date))[1] as title,
        (array_agg(company_name    order by snapshot_date))[1] as company_name,
        (array_agg(salary_text     order by snapshot_date))[1] as salary_text,
        (array_agg(levels_vi::text order by snapshot_date))[1] as levels_vi,
        (array_agg(experience_text order by snapshot_date))[1] as experience_text,
        (array_agg(work_mode       order by snapshot_date))[1] as work_mode,
        (array_agg(provinces::text order by snapshot_date))[1] as provinces,
        (array_agg(skills::text    order by snapshot_date))[1] as skills,
        (array_agg(attributes_hash order by snapshot_date))[1] as attributes_hash
    from numbered
    group by source, job_key, job_id, version_number
)

select
    {{ dbt.hash("job_key || '-' || version_number::text") }} as job_version_key,
    source,
    job_key,
    job_id,
    version_number,
    valid_from,
    lead(valid_from) over (partition by job_key order by version_number) - 1 as valid_to,
    lead(valid_from) over (partition by job_key order by version_number) is null as is_current,
    last_seen_in_version,
    title,
    company_name,
    salary_text,
    levels_vi,
    experience_text,
    work_mode,
    provinces,
    skills,
    attributes_hash
from versions
