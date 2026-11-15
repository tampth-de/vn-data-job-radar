-- SCD2 integrity: for each job, versions must not overlap and exactly one is current.

with ordered as (
    select
        job_id,
        version_number,
        valid_from,
        valid_to,
        is_current,
        lead(valid_from) over (partition by job_id order by version_number) as next_from
    from {{ ref('dim_job_history') }}
),

overlapping_versions as (  -- note: "overlaps" is a reserved word in Postgres
    select job_id, 'overlap or inverted range' as problem
    from ordered
    where (valid_to is not null and valid_to < valid_from)
       or (next_from is not null and valid_to >= next_from)
),

current_count as (
    select job_id, 'not exactly one current version' as problem
    from {{ ref('dim_job_history') }}
    group by job_id
    having count(*) filter (where is_current) <> 1
)

select * from overlapping_versions
union all
select * from current_count
