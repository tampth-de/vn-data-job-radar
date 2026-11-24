"""'Job finder' dashboard: filter active Data/AI postings and open them on the source site.

For personal, local use only. The job boards' terms do not allow redistributing
listings, so this dashboard must not be published (a public site may show aggregates only).

Every filter is optional: Metabase drops a [[ ... ]] block when its variable is empty.
"""

ROLE_FAMILIES = ["data_engineer", "data_analyst", "data_scientist", "ai_engineer", "data_ai_lead",
                 "database_admin", "data_governance", "data_annotation"]
SOURCES = ["topdev", "careerlink"]
LEVELS = ["Intern", "Junior", "Middle", "Senior", "Lead", "Manager", "Director"]
CITIES = ["Hà Nội", "Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ"]
WORK_MODES = ["onsite", "remote", "hybrid"]

# Dashboard filters. `slug` must equal the SQL variable name used by the cards.
PARAMETERS = [
    {"slug": "keyword", "name": "Title contains", "kind": "text"},
    {"slug": "role", "name": "Role", "kind": "text", "values": ROLE_FAMILIES},
    {"slug": "city", "name": "City", "kind": "text", "values": CITIES},
    {"slug": "skill", "name": "Skill (e.g. python, spark, power bi)", "kind": "text"},
    {"slug": "level", "name": "Level", "kind": "text", "values": LEVELS},
    {"slug": "work_mode", "name": "Work mode", "kind": "text", "values": WORK_MODES},
    {"slug": "my_years", "name": "My years of experience", "kind": "number"},
    {"slug": "min_salary", "name": "Min salary (million VND/month)", "kind": "number"},
    {"slug": "days", "name": "Posted in the last N days", "kind": "number"},
    {"slug": "source", "name": "Source", "kind": "text", "values": SOURCES},
]

FILTERS = """
    f.is_active and f.is_data_ai_role
    [[and f.title ilike '%' || {{keyword}} || '%']]
    [[and f.role_family = {{role}}]]
    [[and exists (select 1 from unnest(f.provinces) p where p ilike '%' || {{city}} || '%')]]
    [[and exists (
        select 1 from marts.bridge_job_skills b
        where b.job_key = f.job_key
          and b.skill = coalesce(
                (select d.skill from reference.skill_dictionary d where d.alias = lower(trim({{skill}}))),
                lower(trim({{skill}})))
    )]]
    [[and {{level}} = any(f.levels_en)]]
    [[and f.work_mode = {{work_mode}}]]
    [[and coalesce(f.experience_years_min, 0) <= {{my_years}}]]
    [[and (f.salary_is_negotiable
           or coalesce(f.salary_max_high_vnd, f.salary_estimate_max_vnd) >= {{min_salary}} * 1000000)]]
    [[and f.first_seen_date >= current_date - {{days}}::int]]
    [[and f.source = {{source}}]]
"""

ALL_TAGS = {p["slug"]: p["kind"] for p in PARAMETERS}

CARDS = [
    {
        "name": "Matching jobs",
        "description": "Active Data/AI postings matching the filters.",
        "sql": f"select count(distinct f.posting_key) as jobs from marts.fct_job_postings f where {FILTERS}",
        "display": "scalar", "viz": {},
        "layout": (0, 0, 6, 3),
        "tags": ALL_TAGS,
    },
    {
        "name": "Matching companies",
        "description": None,
        "sql": f"select count(distinct f.company_name) as companies from marts.fct_job_postings f where {FILTERS}",
        "display": "scalar", "viz": {},
        "layout": (0, 6, 6, 3),
        "tags": ALL_TAGS,
    },
    {
        "name": "Most requested skills in matching jobs",
        "description": "Use it to see what to learn for the roles you filtered.",
        "sql": f"""
            select b.skill, count(distinct f.posting_key) as jobs
            from marts.fct_job_postings f
            join marts.bridge_job_skills b on b.job_key = f.job_key
            where {FILTERS}
            group by 1 order by 2 desc, 1
            limit 10
        """,
        "display": "row", "viz": {"graph.dimensions": ["skill"], "graph.metrics": ["jobs"]},
        "layout": (0, 12, 12, 7),
        "tags": ALL_TAGS,
    },
    {
        "name": "Jobs for you",
        "description": "Newest first. 'Apply' opens the posting on its source site (topdev.vn or careerlink.vn).",
        "sql": f"""
            select
                f.first_seen_date                                    as posted_seen,
                f.source,
                f.title,
                f.company_name                                       as company,
                f.role_family                                        as role,
                array_to_string(f.levels_en, ', ')                   as level,
                case
                    when f.salary_is_negotiable then 'Negotiable'
                    when f.salary_max_high_vnd is null then coalesce(nullif(f.salary_text, ''), '-')
                    else coalesce(round(f.salary_min_low_vnd / 1e6)::text, '?') || '–'
                         || round(f.salary_max_high_vnd / 1e6)::text || 'M VND'
                end                                                  as salary,
                case when f.experience_years_min is null then '-'
                     when f.experience_years_min = 0 then 'none'
                     else f.experience_years_min || '+ yrs' end      as experience,
                f.primary_province                                   as city,
                f.work_mode,
                (select string_agg(b.skill, ', ' order by b.skill)
                 from marts.bridge_job_skills b where b.job_key = f.job_key) as skills,
                f.last_seen_date - f.first_seen_date + 1             as days_listed,
                f.same_posting_on                                    as also_on,
                f.job_url                                            as apply
            from marts.fct_job_postings f
            where {FILTERS}
            order by f.first_seen_date desc, f.job_key desc
        """,
        "display": "table",
        "viz": {"column_settings": {'["name","apply"]': {"view_as": "link", "link_text": "Apply ↗"}}},
        "layout": (3, 0, 12, 4),
        "tags": ALL_TAGS,
    },
]

# The table is the main thing: give it the full width below the summary row.
CARDS[3]["layout"] = (7, 0, 24, 12)

DASHBOARD = {
    "name": "Job finder (personal use)",
    "description": "Filter active Data/AI postings (TopDev + CareerLink) and open them on the source site. "
                   "Local only: the job boards' terms do not allow republishing listings.",
    "cards": CARDS,
    "parameters": PARAMETERS,
}
