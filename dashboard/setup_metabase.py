"""Create (or re-create) the Job Radar dashboard in a local Metabase, from code.

    docker compose up -d
    python -m dashboard.setup_metabase

Steps: first-time admin setup (or login) -> register the warehouse -> collection ->
archive the previous dashboard and cards -> create cards from dashboard/cards.py ->
lay them out on a new dashboard. Safe to re-run.
"""

import logging
import os
import time

import httpx
from dotenv import load_dotenv

from dashboard.cards import CARDS
from ingestion.common import setup_logging

load_dotenv()

MB_URL = os.getenv("METABASE_URL", "http://localhost:3000")
ADMIN_EMAIL = os.getenv("METABASE_ADMIN_EMAIL", "admin@radar.local")
ADMIN_PASSWORD = os.environ.get("METABASE_ADMIN_PASSWORD", "")
DB_NAME = "Radar warehouse"
COLLECTION_NAME = "Job Radar"
DASHBOARD_NAME = "Vietnam Data/AI Job Radar"

# Metabase runs inside Docker, so it reaches the warehouse by its compose service name.
WAREHOUSE_DETAILS = {
    "host": "warehouse",
    "port": 5432,
    "dbname": os.getenv("WAREHOUSE_DB", "radar"),
    "user": os.getenv("WAREHOUSE_USER", "radar"),
    "password": os.getenv("WAREHOUSE_PASSWORD", "radar"),
    "ssl": False,
}

log = logging.getLogger(__name__)


def as_list(payload) -> list:
    """Some Metabase endpoints return a list, others {"data": [...]}."""
    return payload["data"] if isinstance(payload, dict) and "data" in payload else payload


def wait_until_healthy(client: httpx.Client, timeout_s: int = 300) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if client.get("/api/health").json().get("status") == "ok":
                return
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(5)
    raise TimeoutError(f"Metabase not healthy at {MB_URL} after {timeout_s}s")


def authenticate(client: httpx.Client) -> None:
    if not ADMIN_PASSWORD:
        raise SystemExit("Set METABASE_ADMIN_PASSWORD in .env first (see .env.example).")
    props = client.get("/api/session/properties").json()
    if props.get("setup-token") and not props.get("has-user-setup"):
        log.info("First run: creating the admin user")
        resp = client.post("/api/setup", json={
            "token": props["setup-token"],
            "user": {
                "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD,
                "first_name": "Radar", "last_name": "Admin", "site_name": "Job Radar",
            },
            "prefs": {"site_name": "Job Radar", "site_locale": "en", "allow_tracking": False},
        })
    else:
        resp = client.post("/api/session", json={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    resp.raise_for_status()
    client.headers["X-Metabase-Session"] = resp.json()["id"]


def ensure_database(client: httpx.Client) -> int:
    for db in as_list(client.get("/api/database").json()):
        if db["name"] == DB_NAME:
            return db["id"]
    log.info("Registering the warehouse in Metabase")
    resp = client.post("/api/database", json={"engine": "postgres", "name": DB_NAME, "details": WAREHOUSE_DETAILS})
    resp.raise_for_status()
    return resp.json()["id"]


def ensure_collection(client: httpx.Client) -> int:
    for coll in as_list(client.get("/api/collection").json()):
        if coll.get("name") == COLLECTION_NAME and not coll.get("archived"):
            return coll["id"]
    resp = client.post("/api/collection", json={"name": COLLECTION_NAME, "color": "#509EE3"})
    resp.raise_for_status()
    return resp.json()["id"]


def archive_previous(client: httpx.Client, collection_id: int) -> None:
    items = as_list(client.get(f"/api/collection/{collection_id}/items").json())
    for item in items:
        if item["model"] == "dashboard":
            client.put(f"/api/dashboard/{item['id']}", json={"archived": True}).raise_for_status()
        elif item["model"] == "card":
            client.put(f"/api/card/{item['id']}", json={"archived": True}).raise_for_status()
    if items:
        log.info("Archived %d previous items", len(items))


def create_dashboard(client: httpx.Client, db_id: int, collection_id: int) -> int:
    dashcards = []
    for i, (name, description, sql, display, viz, (row, col, width, height)) in enumerate(CARDS, start=1):
        resp = client.post("/api/card", json={
            "name": name,
            "description": description,
            "collection_id": collection_id,
            "display": display,
            "visualization_settings": viz,
            "dataset_query": {"type": "native", "database": db_id, "native": {"query": sql.strip()}},
        })
        resp.raise_for_status()
        dashcards.append({
            "id": -i, "card_id": resp.json()["id"],
            "row": row, "col": col, "size_x": width, "size_y": height,
            "parameter_mappings": [], "visualization_settings": {},
        })

    resp = client.post("/api/dashboard", json={
        "name": DASHBOARD_NAME,
        "collection_id": collection_id,
        "description": "Daily snapshot of the Data/AI job market in Vietnam. Source: topdev.vn public listings.",
    })
    resp.raise_for_status()
    dashboard_id = resp.json()["id"]
    client.put(f"/api/dashboard/{dashboard_id}", json={"dashcards": dashcards}).raise_for_status()
    return dashboard_id


def main() -> None:
    setup_logging()
    with httpx.Client(base_url=MB_URL, timeout=60) as client:
        wait_until_healthy(client)
        authenticate(client)
        db_id = ensure_database(client)
        collection_id = ensure_collection(client)
        archive_previous(client, collection_id)
        dashboard_id = create_dashboard(client, db_id, collection_id)
    log.info("Dashboard ready: %s/dashboard/%d (%d cards)", MB_URL, dashboard_id, len(CARDS))


if __name__ == "__main__":
    main()
