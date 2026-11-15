-- One row per job per day it was seen on TopDev (a daily "snapshot").
-- A job found by several keywords on the same day appears once, with all keywords listed.

with source as (
    select * from {{ source('raw', 'topdev_jobs') }}
),

deduplicated as (
    select
        dt,
        job_id,
        -- same job, same day -> identical payload, keep any one of them
        (array_agg(payload order by keyword, page))[1] as payload,
        array_agg(distinct keyword order by keyword)  as matched_keywords
    from source
    group by dt, job_id
),

parsed as (
    select
        dt                                                   as snapshot_date,
        job_id,
        payload ->> 'title'                                  as title,
        payload -> 'company' ->> 'id'                        as company_id,
        payload -> 'company' ->> 'display_name'              as company_name,
        payload ->> 'detail_url'                             as job_url,

        -- seniority & experience
        string_to_array(payload ->> 'job_levels_str', ', ')  as levels_vi,
        payload ->> 'experiences_str'                        as experience_text,
        -- "1 năm, 3 năm" -> 1..3 ; "Không yêu cầu" (not required) -> 0..0
        case when payload ->> 'experiences_str' = 'Không yêu cầu' then 0 else
            (select min(m[1]::int) from regexp_matches(coalesce(payload ->> 'experiences_str', ''), '(\d+)', 'g') m)
        end                                                  as experience_years_min,
        case when payload ->> 'experiences_str' = 'Không yêu cầu' then 0 else
            (select max(m[1]::int) from regexp_matches(coalesce(payload ->> 'experiences_str', ''), '(\d+)', 'g') m)
        end                                                  as experience_years_max,

        -- work mode: "Trực tiếp" = on site, "Từ xa" = remote
        case payload ->> 'job_types_str'
            when 'Trực tiếp' then 'onsite'
            when 'Từ xa' then 'remote'
            else lower(payload ->> 'job_types_str')
        end                                                  as work_mode,

        -- location
        array(select jsonb_array_elements_text(payload -> 'addresses' -> 'address_region_array'))
                                                             as provinces,

        -- skills as given by the employer
        array(select jsonb_array_elements_text(payload -> 'skills_arr'))
                                                             as skills,

        -- salary: is_negotiable comes as "0"/"1" or 0/1 depending on the job
        (payload -> 'salary' ->> 'is_negotiable') = '1'      as salary_is_negotiable,
        payload -> 'salary' ->> 'currency'                   as salary_currency,
        payload -> 'salary' ->> 'unit'                       as salary_unit,
        payload -> 'salary' ->> 'value'                      as salary_text,
        {{ masked_amount_low("payload -> 'salary' ->> 'min'") }}  as salary_min_low,
        {{ masked_amount_high("payload -> 'salary' ->> 'max'") }} as salary_max_high,
        nullif((payload -> 'salary' ->> 'min_estimate')::numeric, 0) as salary_estimate_min,
        nullif((payload -> 'salary' ->> 'max_estimate')::numeric, 0) as salary_estimate_max,

        to_date(payload -> 'published' ->> 'date', 'DD-MM-YYYY') as published_date,
        to_date(payload -> 'refreshed' ->> 'date', 'DD-MM-YYYY') as refreshed_date,
        matched_keywords
    from deduplicated
)

select * from parsed
