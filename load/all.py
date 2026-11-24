"""Load every source's raw files into the warehouse.

    python -m load.all                              # data/raw
    python -m load.all --raw-root tests/fixtures/raw  # CI fixtures
"""

import argparse
import logging
from pathlib import Path

from ingestion.common import setup_logging
from load import careerlink, topdev

log = logging.getLogger(__name__)


def load_all(raw_root: Path | None = None) -> dict:
    return {"topdev": topdev.load(raw_root), "careerlink": careerlink.load(raw_root)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-root", type=Path, default=None)
    args = parser.parse_args()
    setup_logging()
    result = load_all(args.raw_root)
    log.info("Done: topdev %d days, careerlink %d days / %d postings",
             len(result["topdev"]), len(result["careerlink"]["days"]), result["careerlink"]["postings"])
