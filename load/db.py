"""Warehouse connection settings, read from environment variables (or a local .env file).

psycopg2 is used (not psycopg 3) because dbt-postgres already depends on it, so the
project needs a single Postgres driver.
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def connect():
    return psycopg2.connect(
        host=os.getenv("WAREHOUSE_HOST", "localhost"),
        port=int(os.getenv("WAREHOUSE_PORT", "5433")),
        user=os.getenv("WAREHOUSE_USER", "radar"),
        password=os.getenv("WAREHOUSE_PASSWORD", "radar"),
        dbname=os.getenv("WAREHOUSE_DB", "radar"),
    )
