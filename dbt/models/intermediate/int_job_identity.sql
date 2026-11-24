-- Cross-source deduplication (entity resolution): the same ad posted on TopDev and
-- CareerLink gets one posting_key.
--
-- A TopDev job and a CareerLink job are the same posting when
--   * their companies match after normalization (accents and legal boilerplate such as
--     "Công ty TNHH ... Việt Nam" removed): equal, or trigram similarity >= 0.8, and
--     neither is an anonymous employer ("CareerLink's Client", "confidential", ...)
--   * their normalized titles have trigram similarity >= 0.5
--   * they are each other's best match (one-to-one)
-- posting_key = the smallest job_key of the pair ('careerlink:...' sorts first, which
-- also keeps the source with exact salaries as the canonical row).
-- Matching uses each job's latest title and company.

{% set min_company_similarity = 0.8 %}
{% set min_title_similarity = 0.5 %}

with latest as (
    select distinct on (job_key)
        job_key,
        source,
        {{ normalize_company('company_name') }} as company_norm,
        {{ normalize_title('title') }}          as title_norm
    from {{ ref('int_job_snapshots') }}
    order by job_key, snapshot_date desc
),

candidates as (
    select
        a.job_key                                        as job_key_a,
        b.job_key                                        as job_key_b,
        public.similarity(a.company_norm, b.company_norm) as company_similarity,
        public.similarity(a.title_norm, b.title_norm)     as title_similarity
    from latest a
    join latest b
      on a.source < b.source                           -- different sources, each pair once
    where a.company_norm <> '' and b.company_norm <> ''
      and a.company_norm !~ '(client|confidential|bao mat|an danh|headhunt)'
      and b.company_norm !~ '(client|confidential|bao mat|an danh|headhunt)'
      and (a.company_norm = b.company_norm
           or public.similarity(a.company_norm, b.company_norm) >= {{ min_company_similarity }})
      and public.similarity(a.title_norm, b.title_norm) >= {{ min_title_similarity }}
),

ranked as (
    select
        *,
        row_number() over (partition by job_key_a order by title_similarity desc, company_similarity desc, job_key_b) as rank_a,
        row_number() over (partition by job_key_b order by title_similarity desc, company_similarity desc, job_key_a) as rank_b
    from candidates
),

matches as (   -- mutual best matches only
    select job_key_a, job_key_b, title_similarity, company_similarity
    from ranked
    where rank_a = 1 and rank_b = 1
),

pairs as (
    select job_key_a as job_key, job_key_b as matched_job_key, title_similarity, company_similarity from matches
    union all
    select job_key_b, job_key_a, title_similarity, company_similarity from matches
)

select
    l.job_key,
    coalesce(least(l.job_key, p.matched_job_key), l.job_key) as posting_key,
    p.matched_job_key,
    round(p.title_similarity::numeric, 2)   as match_title_similarity,
    round(p.company_similarity::numeric, 2) as match_company_similarity
from latest l
left join pairs p using (job_key)
