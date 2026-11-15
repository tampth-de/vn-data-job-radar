# Vietnam Data/AI Job Radar

[![CI](https://github.com/tampth-de/vn-data-job-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/tampth-de/vn-data-job-radar/actions/workflows/ci.yml)
[![Daily ingest](https://github.com/tampth-de/vn-data-job-radar/actions/workflows/daily_ingest.yml/badge.svg)](https://github.com/tampth-de/vn-data-job-radar/actions/workflows/daily_ingest.yml)

An end-to-end batch data pipeline that tracks the Data & AI job market in Vietnam:
which skills are in demand, how salaries vary by seniority and city, and how the
market changes week over week.

> **Status:** 🚧 Work in progress. See the [Roadmap](#roadmap).

## Questions this project answers

1. Which skills are most requested for Data Engineer / Data Analyst / Data Scientist / AI Engineer roles, and which are trending up?
2. What are the salary ranges by seniority level and city?
3. Which companies are hiring the most Data/AI talent?
4. What share of jobs are remote/hybrid, and what share require English?
5. How long does a job posting typically stay open?
6. Which skills tend to appear together (e.g. Spark + Airflow)?

## Architecture

```
TopDev public API
        │  ingestion/  Python, daily at 08:00 (GitHub Actions), retries, idempotent
        ▼
Bronze  raw JSON, data/raw/<source>/dt=YYYY-MM-DD/   (private data repo)
        │  load/       Python → PostgreSQL, one transaction per day partition
        ▼
raw.*           untouched JSON in jsonb
        │  dbt
        ▼
staging.*       typed columns, one row per job per day
intermediate.*  business rules (role classification)
marts.*         fct_job_postings, bridge_job_skills, agg_skill_demand_daily
        ▼
Dashboard (planned: Metabase)
```

Runtime: PostgreSQL 17 in Docker Compose · Transformations: dbt Core · Tests: pytest + dbt tests

## Data model

| Model | Grain | Highlights |
|---|---|---|
| `stg_topdev__job_snapshots` | job × day | Dedups jobs found by several keywords; parses masked salaries into ranges, experience years, provinces, skills |
| `int_job_snapshots_classified` | job × day | Assigns a role family from ordered regex rules in a seed (`role_rules.csv`); flags non-data noise such as "Telesales – data có sẵn" |
| `fct_job_postings` | job | Latest attributes + lifecycle (`first_seen_date`, `last_seen_date`, `is_active`), seniority range, salary in VND |
| `bridge_job_skills` | job × skill | Normalized skill names |
| `agg_skill_demand_daily` | day × skill | Share of Data/AI postings requiring each skill |

Two data problems worth noting:

- **Masked salaries.** Anonymous visitors see `"1*******"`. That still means *an 8-digit
  number starting with 1*, i.e. 10–19.99M VND, so salaries become ranges
  (`salary_min_low`, `salary_max_high`) via a dbt macro.
- **Noisy keyword search.** Only ~45% of jobs returned for "data"/"AI" are actual
  Data/AI roles; the rest are sales/marketing posts mentioning "data". A rule-based
  classifier keeps marts clean.

## Data sources

Currently scheduled: **TopDev** ([topdev.vn](https://topdev.vn)) via its public JSON API.

See [docs/source_survey.md](docs/source_survey.md) for how each source was evaluated,
including a review of each site's `robots.txt` and Terms of Service. Requests are
made at a low rate with an honest User-Agent. Raw data is kept in a private
repository, no personal data (recruiter emails/phones) is stored, nothing is used
commercially, and only aggregated statistics are published, credited to the source.

## Project structure

```
ingestion/          Scrapers, one sub-package per source + shared helpers (common.py)
load/               Loads raw files into the warehouse `raw` schema
dbt/                dbt project: staging, intermediate, marts, seeds, macros, tests
tests/              Unit tests (pytest, no network)
docs/               Source survey and design notes
data/               Local clone of the private data repo (git-ignored)
.github/workflows/  Scheduled daily ingestion
docker-compose.yml  Local PostgreSQL warehouse (port 5433)
```

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows
pip install -r requirements.txt
copy .env.example .env                 # warehouse connection settings

docker compose up -d                   # PostgreSQL on localhost:5433
python -m ingestion.topdev.fetch_jobs  # or: git clone <data repo> data
python -m load.topdev                  # raw files -> raw.topdev_jobs
cd dbt && dbt build --profiles-dir .   # seeds, models and tests
python -m pytest                       # unit tests
```

## Scheduling and data quality

**Daily** ([daily_ingest.yml](.github/workflows/daily_ingest.yml), 08:00 Vietnam time):

1. unit tests → fetch TopDev → commit raw files to the **private** data repo
   (deploy key scoped to that repo only, so scraped content never lands in this public repo)
2. load the **full history** into a throwaway PostgreSQL service container
3. `dbt build` with production thresholds: all model tests plus a health check that
   fails if the latest run found fewer than 10 jobs or is older than 2 days
   (a sudden drop usually means the site changed or blocked us)
4. publish an aggregated summary (active jobs, role families, top skills) on the run page

A failed check turns the run red and GitHub emails the owner. Raw data is always
committed before validation, so nothing is lost when a check fails.

**On every push** ([ci.yml](.github/workflows/ci.yml)): unit tests, then the whole
pipeline end to end on synthetic fixtures ([tests/fixtures/raw](tests/fixtures/raw)):
load → `dbt build` → assertions on the marts (dedup, lifecycle, classification,
masked salary ranges, skill normalization).

| Layer | Tests |
|---|---|
| Python | 10 unit tests (paging, retries, idempotency, HTML parsing), 7 end-to-end tests |
| dbt | not-null / unique / accepted values / relationships, custom `unique_combination`, masked-salary macro test, ingestion health check |

## Roadmap

- [x] Survey data sources, review robots.txt and Terms of Service
- [x] TopDev ingestion → raw JSON (multi-keyword, pagination, retries, idempotent daily partition)
- [x] Daily schedule (GitHub Actions → private data repo)
- [x] ITviec parser (HTML, BeautifulSoup) — not scheduled: ITviec's terms require written consent ([details](docs/source_survey.md#terms-of-service-review-2026-11-15))
- [x] PostgreSQL warehouse (Docker) + idempotent raw loader
- [x] dbt staging / intermediate / marts with tests, masked-salary parsing, role classification
- [x] Job lifecycle: first seen / last seen / active
- [ ] Track attribute changes over time (SCD2 with dbt snapshots)
- [ ] Skill synonym mapping (e.g. "postgres" = "postgresql")
- [x] CI (end-to-end on fixtures) + daily data quality checks on real data
- [ ] Airflow orchestration
- [ ] Metabase dashboard
