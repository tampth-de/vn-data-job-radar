-- One row per job per day it was listed on CareerLink search pages, enriched with the
-- job's schema.org JobPosting (fetched once per job). Jobs whose page has not been
-- fetched yet still appear, with only the listing title (has_details = false).

with listings as (
    select
        dt,
        job_id,
        min(listing_title)                           as listing_title,
        min(job_path)                                as job_path,
        array_agg(distinct keyword order by keyword) as matched_keywords
    from {{ source('raw', 'careerlink_listings') }}
    group by dt, job_id
),

postings as (
    select
        job_id,
        payload ->> 'url'          as url,
        payload -> 'job_posting'   as p
    from {{ source('raw', 'careerlink_postings') }}
),

joined as (
    select
        l.*,
        po.url,
        po.p,
        po.p -> 'baseSalary' -> 'value' as sal,
        case
            when jsonb_typeof(po.p -> 'experienceRequirements') = 'object'
            then (po.p -> 'experienceRequirements' ->> 'monthsOfExperience')::int
        end as experience_months,
        case jsonb_typeof(po.p -> 'jobLocation')
            when 'array'  then po.p -> 'jobLocation'
            when 'object' then jsonb_build_array(po.p -> 'jobLocation')
            else '[]'::jsonb
        end as locations
    from listings l
    left join postings po using (job_id)
)

select
    dt                                                        as snapshot_date,
    job_id,
    coalesce(p ->> 'title', listing_title)                    as title,
    substring(p -> 'hiringOrganization' ->> 'sameAs' from '/(\d+)$') as company_id,
    p -> 'hiringOrganization' ->> 'name'                      as company_name,
    coalesce(url, 'https://www.careerlink.vn' || job_path)    as job_url,
    case jsonb_typeof(p -> 'occupationalCategory')
        when 'object' then p -> 'occupationalCategory' ->> 'name'
        when 'string' then p ->> 'occupationalCategory'
    end                                                       as category_name,

    -- experience: months in JSON-LD, or the text "no requirements"
    coalesce(experience_months || ' months', p ->> 'experienceRequirements') as experience_text,
    case
        when experience_months is not null then experience_months / 12
        when p ->> 'experienceRequirements' ilike 'no requirement%' then 0
    end                                                       as experience_years_min,
    case
        when experience_months is not null then experience_months / 12
        when p ->> 'experienceRequirements' ilike 'no requirement%' then 0
    end                                                       as experience_years_max,

    case
        when p is null then null
        when p ->> 'jobLocationType' = 'TELECOMMUTE' then 'remote'
        else 'onsite'
    end                                                       as work_mode,

    array(
        select distinct coalesce(loc -> 'address' ->> 'addressRegion', loc -> 'address' ->> 'addressLocality')
        from jsonb_array_elements(locations) as loc
        where coalesce(loc -> 'address' ->> 'addressRegion', loc -> 'address' ->> 'addressLocality') is not null
    )                                                         as provinces,

    -- salary is shown in full on CareerLink: {"minValue", "maxValue"} or {"value": "Thương lượng"}
    (sal ->> 'minValue') is null and (sal ->> 'maxValue') is null
        and coalesce(sal ->> 'value', '') !~ '^[0-9.]+$'      as salary_is_negotiable,
    p -> 'baseSalary' ->> 'currency'                          as salary_currency,
    sal ->> 'unitText'                                        as salary_unit,
    case
        when (sal ->> 'minValue') is not null or (sal ->> 'maxValue') is not null
            then concat_ws(' - ', sal ->> 'minValue', sal ->> 'maxValue') || ' ' || coalesce(p -> 'baseSalary' ->> 'currency', '')
        else sal ->> 'value'
    end                                                       as salary_text,
    coalesce((sal ->> 'minValue')::numeric,
             case when sal ->> 'value' ~ '^[0-9.]+$' then (sal ->> 'value')::numeric end) as salary_min,
    coalesce((sal ->> 'maxValue')::numeric,
             case when sal ->> 'value' ~ '^[0-9.]+$' then (sal ->> 'value')::numeric end) as salary_max,

    (p ->> 'datePosted')::date                                as published_date,
    (p ->> 'validThrough')::timestamptz::date                 as valid_through_date,
    trim(regexp_replace(regexp_replace(coalesce(p ->> 'description', ''), '<[^>]+>', ' ', 'g'), '\s+', ' ', 'g'))
                                                              as description_text,
    matched_keywords,
    p is not null                                             as has_details
from joined
