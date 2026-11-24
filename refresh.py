"""One command to bring the local dashboard up to date.

    python refresh.py                      # or double-click refresh.cmd on Windows
    python refresh.py --rebuild-dashboard  # also re-create the Metabase dashboard

Steps:
  1. make sure Docker is running and start the warehouse + Metabase containers
  2. pull the latest raw data (data/ is a clone of the private data repo)
  3. load raw files into the warehouse (idempotent)
  4. dbt build: models + data tests
  5. create the dashboard if it does not exist yet (or always, with --rebuild-dashboard)
  6. print today's summary
"""

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DBT_DIR = ROOT / "dbt"
DOCKER_DESKTOP_WIN = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "Docker Desktop.exe"

log = logging.getLogger("refresh")


class StepFailed(Exception):
    pass


def run(cmd: list[str], cwd: Path = ROOT, quiet: bool = False) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(cmd, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                            capture_output=quiet)
    if result.returncode != 0:
        if quiet and result.stderr:
            log.error(result.stderr.strip()[-2000:])
        raise StepFailed(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def docker_is_up() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def ensure_docker() -> None:
    if shutil.which("docker") is None:
        raise StepFailed("Docker CLI not found. Install Docker Desktop first.")
    if docker_is_up():
        return
    if platform.system() == "Windows" and DOCKER_DESKTOP_WIN.exists():
        log.info("Starting Docker Desktop...")
        subprocess.Popen([str(DOCKER_DESKTOP_WIN)])
        for _ in range(60):  # up to ~3 minutes
            time.sleep(3)
            if docker_is_up():
                return
    raise StepFailed("Docker engine is not running. Start Docker Desktop and try again.")


def dbt_command() -> list[str]:
    # Run dbt through the Python interpreter instead of the `dbt.exe` launcher that pip
    # generates: Windows Smart App Control can block that unsigned launcher, while
    # python.exe itself is signed.
    return [sys.executable, "-c", "from dbt.cli.main import cli; cli()"]


def step_containers() -> None:
    ensure_docker()
    run(["docker", "compose", "up", "-d", "--wait"], quiet=True)


def step_pull_data() -> None:
    if not (DATA_DIR / ".git").exists():
        log.warning("data/ is not a git clone of the data repo: skipping pull "
                    "(clone it with: git clone https://github.com/<you>/vn-data-job-radar-data.git data)")
        return
    out = run(["git", "-C", str(DATA_DIR), "pull", "--ff-only"], quiet=True).stdout.strip()
    log.info("data repo: %s", out.splitlines()[-1] if out else "up to date")


def step_load() -> None:
    from load.all import load_all
    result = load_all()
    log.info("loaded topdev %d days, careerlink %d days / %d job pages",
             len(result["topdev"]), len(result["careerlink"]["days"]), result["careerlink"]["postings"])


def step_dbt() -> None:
    run([*dbt_command(), "build", "--profiles-dir", "."], cwd=DBT_DIR)


def step_dashboard(rebuild: bool) -> dict[str, str]:
    """Ensure every dashboard exists (re-create all if one is missing). Returns name -> URL."""
    import httpx

    from dashboard import setup_metabase as mb
    from dashboard.job_finder import DASHBOARD as JOB_FINDER

    wanted = {mb.MARKET_DASHBOARD["name"], JOB_FINDER["name"]}
    with httpx.Client(base_url=mb.MB_URL, timeout=60) as client:
        mb.wait_until_healthy(client)
        mb.authenticate(client)
        collection_id = mb.ensure_collection(client)
        items = mb.as_list(client.get(f"/api/collection/{collection_id}/items").json())
        existing = {i["name"]: i["id"] for i in items if i["model"] == "dashboard"}
        if rebuild or not wanted <= existing.keys():
            existing = mb.create_all(client)
        return {name: f"{mb.MB_URL}/dashboard/{existing[name]}" for name in sorted(wanted)}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Vietnamese text on the Windows console
    parser = argparse.ArgumentParser(description="Refresh the local warehouse and dashboard.")
    parser.add_argument("--rebuild-dashboard", action="store_true", help="re-create the Metabase dashboard")
    args = parser.parse_args()

    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from ingestion.common import setup_logging
    setup_logging()

    steps = [
        ("Start containers", step_containers),
        ("Pull latest raw data", step_pull_data),
        ("Load into warehouse", step_load),
        ("dbt build + tests", step_dbt),
    ]
    try:
        for i, (name, func) in enumerate(steps, start=1):
            log.info("[%d/%d] %s", i, len(steps) + 1, name)
            func()
        log.info("[%d/%d] Dashboard", len(steps) + 1, len(steps) + 1)
        urls = step_dashboard(args.rebuild_dashboard)
    except StepFailed as exc:
        log.error("Refresh stopped: %s", exc)
        return 1

    from load.summary import build_summary
    print("\n" + build_summary() + "\n")
    for name, url in urls.items():
        print(f"Dashboard: {url}   ({name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
