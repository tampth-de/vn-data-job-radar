"""Helpers shared by every source: polite HTTP with retries, and dated raw partitions."""

import json
import logging
import os
import shutil
import time
from datetime import date
from pathlib import Path

import httpx

HEADERS = {"User-Agent": "vn-data-job-radar/0.1 (portfolio project)"}
# data/ is a clone of the private data repo, written only by the daily GitHub Actions
# run. Local experiments set RADAR_RAW_ROOT (e.g. data_local/raw) so they never
# modify that clone.
RAW_ROOT = Path(os.getenv("RADAR_RAW_ROOT", "data/raw"))
SLEEP_BETWEEN_REQUESTS = 2.0  # seconds, be polite to the server
MAX_RETRIES = 3

log = logging.getLogger(__name__)


def make_client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)


def polite_pause() -> None:
    time.sleep(SLEEP_BETWEEN_REQUESTS)


def get_with_retries(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
    """GET a URL, retrying network errors, 429 and 5xx with exponential backoff.

    Client errors such as 404 are raised immediately: retrying will not fix them.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TransportError) or (
                exc.response.status_code == 429 or exc.response.status_code >= 500
            )
            if not retryable or attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt  # 2s, 4s, ...
            log.warning("GET %s failed (%s), retry %d in %ds", url, exc, attempt, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


class SourceUnavailable(RuntimeError):
    """The site answered, but with no usable data (blocked, throttled or layout changed)."""


class Partition:
    """A day partition written atomically: data/raw/<source>/dt=<date>/.

    Files are written to a temporary sibling folder (`path`). `commit()` swaps it in
    place of the previous partition, so a re-run on the same day fully replaces that
    day's files (idempotent, no stale files). If the run fails or is never committed,
    the temporary folder is dropped and the previous partition stays untouched: a
    throttled or broken run can never overwrite good data with an empty snapshot.

        with Partition("topdev", run_date) as part:
            write_json(part.path / "x.json", ...)
            part.commit()
    """

    def __init__(self, source: str, run_date: date, raw_root: Path | None = None):
        self.final = (raw_root or RAW_ROOT) / source / f"dt={run_date.isoformat()}"
        # name must not match "dt=*", which the loaders read
        self.path = self.final.with_name(f".tmp_{self.final.name}")
        self.committed = False

    def __enter__(self) -> "Partition":
        if self.path.exists():
            shutil.rmtree(self.path)
        self.path.mkdir(parents=True)
        return self

    def commit(self) -> Path:
        if self.final.exists():
            shutil.rmtree(self.final)
        self.path.rename(self.final)
        self.committed = True
        return self.final

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self.committed and self.path.exists():
            shutil.rmtree(self.path)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # hide per-request URL noise
