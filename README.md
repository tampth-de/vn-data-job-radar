# Vietnam Data/AI Job Radar

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

## Architecture (planned)

```
Job boards (TopDev API, ITviec HTML, ...)
        │  Python ingestion, daily, idempotent
        ▼
Raw / Bronze   →  original JSON/HTML, partitioned by source and date
        ▼
Staging / Silver → parsed, normalized, deduplicated  (PostgreSQL)
        ▼
Marts / Gold   →  star schema built with dbt, tested
        ▼
Dashboard (Metabase)

Orchestration: Airflow  ·  Runtime: Docker Compose  ·  CI: GitHub Actions
```

## Data sources

See [docs/source_survey.md](docs/source_survey.md) for how each source was evaluated.
Only public job listing pages are collected, at a low request rate, respecting
`robots.txt`. No personal data (recruiter emails/phones) is stored, and only
aggregated results are published.

## Project structure

```
ingestion/          Python scrapers, one sub-package per source
tests/              Unit tests (parsers, normalizers)
docs/               Design notes, source survey, data model
data/               Local data lake (git-ignored)
.github/workflows/  Scheduled daily ingestion
```

## Scheduling

A GitHub Actions workflow ([daily_ingest.yml](.github/workflows/daily_ingest.yml))
runs every day at 08:00 Vietnam time: it runs the unit tests, fetches new data and
commits the raw files to a separate **private** data repository, so scraped content
is never published in this public repo.

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Roadmap

- [x] Survey data sources
- [x] TopDev ingestion → raw JSON (multi-keyword, pagination, retries, idempotent daily partition)
- [ ] Daily schedule (GitHub Actions)
- [ ] ITviec ingestion
- [ ] PostgreSQL + dbt staging/marts
- [ ] Salary & skill normalization, cross-source dedup
- [ ] Job lifecycle tracking (SCD2)
- [ ] Data quality tests + CI
- [ ] Airflow orchestration
- [ ] Metabase dashboard
