"""Load CareerLink raw files into the warehouse `raw` schema.

    data/raw/careerlink/dt=YYYY-MM-DD/keyword=<kw>/page_NNN.html  ->  raw.careerlink_listings
        (one row per day, keyword and job seen on the search page)
    data/raw/careerlink/jobs/<job_id>.json                         ->  raw.careerlink_postings
        (one row per job: the JobPosting JSON-LD, fetched once)
    data/raw/careerlink/dt=YYYY-MM-DD/_manifest.json               ->  raw.ingestion_runs

Search pages are HTML, so this loader extracts (job_id, title) from them with the same
parser the scraper uses. Idempotent: each day is replaced inside one transaction, and
postings are upserted by job_id.
"""

import json
import logging
import re
from pathlib import Path

from psycopg2.extras import Json, execute_values

from ingestion.careerlink.parse import parse_job_links
from ingestion.common import RAW_ROOT, setup_logging
from load.db import connect

SOURCE = "careerlink"
PARTITION_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})$")

DDL = """
create schema if not exists raw;

create table if not exists raw.careerlink_listings (
    dt            date        not null,
    keyword       text        not null,
    job_id        bigint      not null,
    listing_title text,
    job_path      text        not null,
    source_file   text        not null,
    loaded_at     timestamptz not null default now()
);
create index if not exists careerlink_listings_dt_idx on raw.careerlink_listings (dt);

create table if not exists raw.careerlink_postings (
    job_id      bigint      primary key,
    payload     jsonb       not null,
    fetched_at  timestamptz,
    source_file text        not null,
    loaded_at   timestamptz not null default now()
);

create table if not exists raw.ingestion_runs (
    source    text        not null,
    dt        date        not null,
    manifest  jsonb       not null,
    loaded_at timestamptz not null default now(),
    primary key (source, dt)
);
"""

log = logging.getLogger(__name__)


def read_listing_partition(partition_dir: Path) -> list[tuple]:
    rows = []
    for file in sorted(partition_dir.glob("keyword=*/page_*.html")):
        keyword = file.parent.name.removeprefix("keyword=")
        for job_id, (path, title) in parse_job_links(file.read_text(encoding="utf-8")).items():
            rows.append((keyword, job_id, title or None, path, file.relative_to(partition_dir.parent).as_posix()))
    return rows


def load(raw_root: Path | None = None) -> dict:
    source_dir = (raw_root or RAW_ROOT) / SOURCE
    summary = {"days": {}, "postings": 0}
    if not source_dir.exists():
        log.info("no CareerLink data under %s", source_dir)
        return summary

    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(DDL)

        for partition_dir in sorted(source_dir.glob("dt=*")):
            match = PARTITION_RE.search(partition_dir.name)
            if not (partition_dir.is_dir() and match):
                continue
            dt = match.group(1)
            rows = read_listing_partition(partition_dir)
            manifest_file = partition_dir / "_manifest.json"
            with conn, conn.cursor() as cur:  # one transaction per day
                cur.execute("delete from raw.careerlink_listings where dt = %s", (dt,))
                execute_values(
                    cur,
                    "insert into raw.careerlink_listings (dt, keyword, job_id, listing_title, job_path, source_file)"
                    " values %s",
                    [(dt, *row) for row in rows],
                )
                if manifest_file.exists():
                    cur.execute(
                        "insert into raw.ingestion_runs (source, dt, manifest) values (%s, %s, %s)"
                        " on conflict (source, dt) do update set manifest = excluded.manifest, loaded_at = now()",
                        (SOURCE, dt, Json(json.loads(manifest_file.read_text(encoding="utf-8")))),
                    )
            summary["days"][dt] = len(rows)
            log.info("careerlink dt=%s: loaded %d listing rows", dt, len(rows))

        postings = []
        for file in sorted((source_dir / "jobs").glob("*.json")):
            doc = json.loads(file.read_text(encoding="utf-8"))
            postings.append((doc["job_id"], Json(doc), doc.get("fetched_at"),
                             file.relative_to(source_dir).as_posix()))
        if postings:
            with conn, conn.cursor() as cur:
                execute_values(
                    cur,
                    "insert into raw.careerlink_postings (job_id, payload, fetched_at, source_file) values %s"
                    " on conflict (job_id) do update set payload = excluded.payload,"
                    " fetched_at = excluded.fetched_at, source_file = excluded.source_file, loaded_at = now()",
                    postings,
                )
        summary["postings"] = len(postings)
        log.info("careerlink: %d job postings upserted", len(postings))
    finally:
        conn.close()
    return summary


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-root", type=Path, default=None)
    args = parser.parse_args()
    setup_logging()
    load(args.raw_root)
