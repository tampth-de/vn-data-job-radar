-- Adds a role family to every daily snapshot using the ordered regex rules in the
-- role_rules seed (first matching rule wins, case-insensitive).
-- Rules run on the title plus, when the source provides one, its own job category
-- (CareerLink: "Kỹ sư dữ liệu", "AI developer", "Phân tích dữ liệu", ...).
-- Keyword search on job boards is noisy ("Telesales - Data có sẵn" matches "data"),
-- so marts use is_data_ai_role to keep only relevant jobs.

with snapshots as (
    select
        *,
        title || coalesce(' | ' || category_name, '') as classification_text
    from {{ ref('int_job_snapshots') }}
),

rules as (
    select * from {{ ref('role_rules') }}
)

select
    s.*,
    coalesce(r.role_family, 'other')                              as role_family,
    coalesce(r.role_family, 'other') not in ('non_data', 'other') as is_data_ai_role
from snapshots s
left join lateral (
    select role_family
    from rules
    where s.classification_text ~* rules.pattern
    order by rule_order
    limit 1
) r on true
