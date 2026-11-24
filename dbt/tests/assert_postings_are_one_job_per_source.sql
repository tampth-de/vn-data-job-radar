-- Dedup integrity: a posting groups at most one job per source (matching is one-to-one).

select i.posting_key, s.source, count(*) as jobs
from {{ ref('int_job_identity') }} i
join (select distinct job_key, source from {{ ref('int_job_snapshots') }}) s using (job_key)
group by 1, 2
having count(*) > 1
