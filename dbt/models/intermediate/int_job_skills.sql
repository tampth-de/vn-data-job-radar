-- One row per (day, job, canonical skill), from two places:
--   1. skill tags given by the source (TopDev), mapped through skill_dictionary
--      ("pyspark" -> spark, "reactjs" -> react); unknown tags keep their cleaned name
--      with category 'uncategorized';
--   2. skills mentioned in the job description (CareerLink has no tags), matched as
--      whole words, using only aliases flagged text_match = true. Ambiguous aliases
--      are excluded: "ai" is also a Vietnamese word ("who"), "go", "r", "sales", ...

with snapshots as (
    select * from {{ ref('int_job_snapshots_classified') }}
),

dictionary as (
    select * from {{ ref('skill_dictionary') }}
),

tags as (
    select
        s.snapshot_date, s.job_key, s.source, s.is_data_ai_role, s.role_family,
        lower(trim(t.skill_raw)) as alias
    from snapshots s
    cross join lateral unnest(s.skills) as t(skill_raw)
    where trim(t.skill_raw) <> ''
),

from_tags as (
    select
        t.snapshot_date, t.job_key, t.source, t.is_data_ai_role, t.role_family,
        coalesce(d.skill, t.alias)                  as skill,
        coalesce(d.skill_category, 'uncategorized') as skill_category
    from tags t
    left join dictionary d on d.alias = t.alias
),

from_text as (
    select
        s.snapshot_date, s.job_key, s.source, s.is_data_ai_role, s.role_family,
        d.skill,
        d.skill_category
    from snapshots s
    join dictionary d
      on d.text_match
     and s.description_text is not null
     -- whole-word match; regex special characters in the alias are escaped (c#, node.js, ci/cd)
     and s.description_text ~* (
            '(^|[^[:alnum:]])'
            || regexp_replace(d.alias, '([.^$*+?()\[\]{}|\\])', '\\\1', 'g')
            || '([^[:alnum:]]|$)'
         )
)

select distinct * from from_tags
union
select distinct * from from_text
