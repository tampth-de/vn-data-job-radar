-- All sources in one shape: one row per (source, job, day).
-- job_key = '<source>:<id>' because ids are only unique within a source.
-- Salaries: TopDev masks them, so low/high are bounds; CareerLink shows exact values.

with topdev as (
    select
        'topdev'                          as source,
        'topdev:' || job_id               as job_key,
        job_id,
        snapshot_date,
        title,
        company_id,
        company_name,
        job_url,
        null::text                        as category_name,
        levels_vi,
        experience_text,
        experience_years_min,
        experience_years_max,
        work_mode,
        provinces,
        skills,
        salary_is_negotiable,
        salary_currency,
        salary_unit,
        salary_text,
        salary_min_low,
        salary_max_high,
        salary_estimate_min,
        salary_estimate_max,
        true                              as salary_is_masked,
        published_date,
        refreshed_date,
        null::date                        as valid_through_date,
        null::text                        as description_text,
        matched_keywords,
        true                              as has_details
    from {{ ref('stg_topdev__job_snapshots') }}
),

careerlink as (
    select
        'careerlink'                      as source,
        'careerlink:' || job_id           as job_key,
        job_id,
        snapshot_date,
        title,
        company_id,
        company_name,
        job_url,
        category_name,
        '{}'::text[]                      as levels_vi,
        experience_text,
        experience_years_min,
        experience_years_max,
        work_mode,
        provinces,
        '{}'::text[]                      as skills,   -- no tags: extracted from description_text later
        salary_is_negotiable,
        salary_currency,
        salary_unit,
        salary_text,
        salary_min                        as salary_min_low,
        salary_max                        as salary_max_high,
        null::numeric                     as salary_estimate_min,
        null::numeric                     as salary_estimate_max,
        false                             as salary_is_masked,
        published_date,
        null::date                        as refreshed_date,
        valid_through_date,
        description_text,
        matched_keywords,
        has_details
    from {{ ref('stg_careerlink__job_snapshots') }}
),

unioned as (
    select * from topdev
    union all
    select * from careerlink
)

select
    source, job_key, job_id, snapshot_date, title, company_id, company_name, job_url, category_name,
    levels_vi, experience_text, experience_years_min, experience_years_max, work_mode,
    -- one spelling per province: "Thành phố Hà Nội" (TopDev) = "Hà Nội" (CareerLink)
    array(
        select regexp_replace(p, '^(Thành phố|Tỉnh)\s+', '')
        from unnest(provinces) with ordinality as t(p, i)
        order by i
    ) as provinces,
    skills, salary_is_negotiable, salary_currency, salary_unit, salary_text,
    salary_min_low, salary_max_high, salary_estimate_min, salary_estimate_max, salary_is_masked,
    published_date, refreshed_date, valid_through_date, description_text, matched_keywords, has_details
from unioned
