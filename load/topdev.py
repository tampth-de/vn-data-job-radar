"""Load TopDev raw JSON files from the data lake into the warehouse `raw` schema.

    data/raw/topdev/dt=YYYY-MM-DD/keyword=<kw>/page_NNN.json  ->  raw.topdev_jobs
    data/raw/topdev/dt=YYYY-MM-DD/_manifest.json               ->  raw.ingestion_runs

Each job is stored as one row with its untouched JSON payload (jsonb). Parsing
into typed columns happens in dbt (staging layer).

Idempotent: each date partition is deleted and re-inserted inside one transaction,
so re-running the loader never duplicates rows and a failure never leaves a
half-loaded day behind.
"""

import json
import logging
import re
from pathlib import Path

from psycopg2.extras import Json, execute_values

from ingestion.common import RAW_ROOT, setup_logging
from load.db import connect

SOURCE = "topdev"
PARTITION_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})$")
KEYWORD_RE = re.compile(r"keyword=(.+)$")
PAGE_RE = re.compile(r"page_(\d+)\.json$")

DDL = """
create schema if not exists raw;

create table if not exists raw.topdev_jobs (
    dt          date        not null,
    keyword     text        not null,
    page        int         not null,
    job_id      bigint      not null,
    payload     jsonb       not null,
    source_file text        not null,
    loaded_at   timestamptz not null default now()
);
create index if not exists topdev_jobs_dt_idx on raw.topdev_jobs (dt);

create table if not exists raw.ingestion_runs (
    source    text        not null,
    dt        date        not null,
    manifest  jsonb       not null,
    loaded_at timestamptz not null default now(),
    primary key (source, dt)
);
"""

log = logging.getLogger(__name__)


def iter_partitions(source_dir: Path):
    for path in sorted(source_dir.glob("dt=*")):
        match = PARTITION_RE.search(path.name)
        if path.is_dir() and match:
            yield match.group(1), path


def read_partition(partition_dir: Path) -> list[tuple]:
    """Return one tuple per job: (keyword, page, job_id, payload, source_file)."""
    rows = []
    for file in sorted(partition_dir.glob("keyword=*/page_*.json")):
        keyword = KEYWORD_RE.search(file.parent.name).group(1)
        page = int(PAGE_RE.search(file.name).group(1))
        data = json.loads(file.read_text(encoding="utf-8"))
        for job in data.get("data", []):
            rows.append((keyword, page, job["id"], job, file.relative_to(partition_dir.parent).as_posix()))
    return rows


def load(raw_root: Path | None = None) -> dict:
    source_dir = (raw_root or RAW_ROOT) / SOURCE
    summary = {}
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(DDL)
        for dt, partition_dir in iter_partitions(source_dir):
            rows = read_partition(partition_dir)
            manifest_file = partition_dir / "_manifest.json"
            # `with conn` = one transaction: commit on success, rollback on any error.
            with conn, conn.cursor() as cur:
                cur.execute("delete from raw.topdev_jobs where dt = %s", (dt,))
                execute_values(
                    cur,
                    "insert into raw.topdev_jobs (dt, keyword, page, job_id, payload, source_file) values %s",
                    [(dt, kw, page, job_id, Json(payload), src) for kw, page, job_id, payload, src in rows],
                )
                if manifest_file.exists():
                    cur.execute(
                        "insert into raw.ingestion_runs (source, dt, manifest) values (%s, %s, %s)"
                        " on conflict (source, dt) do update set manifest = excluded.manifest, loaded_at = now()",
                        (SOURCE, dt, Json(json.loads(manifest_file.read_text(encoding="utf-8")))),
                    )
            summary[dt] = len(rows)
            log.info("dt=%s: loaded %d rows", dt, len(rows))
    finally:
        conn.close()
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-root", type=Path, default=None,
                        help="root of the raw lake (default: data/raw). CI uses tests/fixtures/raw")
    args = parser.parse_args()

    setup_logging()
    result = load(args.raw_root)
    log.info("Done: %d partitions, %d rows", len(result), sum(result.values()))
