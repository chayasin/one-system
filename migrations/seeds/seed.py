#!/usr/bin/env python3
"""
Seed runner — loads all reference data into the database.

Usage:
  # Development (local Docker Compose):
  ENVIRONMENT=development python seed.py

  # Production (against Aurora):
  ENVIRONMENT=production python seed.py

Seeds are idempotent — safe to re-run (all INSERT … ON CONFLICT DO NOTHING).
"""
import json
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load .env
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_repo_root / ".env", override=False)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
SEEDS_DIR = Path(__file__).parent

SEED_FILES = [
    "seed_service_types.sql",
    "seed_complaint_types.sql",
    "seed_closure_reasons.sql",
    "seed_sla_config.sql",
    "seed_handlers.sql",
]

VERIFY_QUERIES = {
    "ref_service_type":  ("SELECT COUNT(*) FROM ref_service_type",  12),
    "ref_complaint_type": ("SELECT COUNT(*) FROM ref_complaint_type", 12),
    "ref_closure_reason": ("SELECT COUNT(*) FROM ref_closure_reason",  5),
    "sla_config":        ("SELECT COUNT(*) FROM sla_config",          4),
    "ref_handler":       ("SELECT COUNT(*) FROM ref_handler",         14),
}


def _get_connection() -> psycopg2.extensions.connection:
    if ENVIRONMENT == "development":
        return psycopg2.connect(
            host=os.environ.get("LOCAL_DB_HOST", "localhost"),
            port=int(os.environ.get("LOCAL_DB_PORT", "5433")),
            dbname=os.environ.get("LOCAL_DB_NAME", "one_system_dev"),
            user=os.environ.get("LOCAL_DB_USER", "postgres"),
            password=os.environ.get("LOCAL_DB_PASSWORD", "localpassword"),
        )

    host = os.environ.get("DB_HOST", "")
    port = int(os.environ.get("DB_PORT", "5432"))
    dbname = os.environ.get("DB_NAME", "one_system")
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")

    if host and not password:
        try:
            import boto3
            region = os.environ.get("AWS_REGION", "ap-southeast-7")
            client = boto3.client("secretsmanager", region_name=region)
            secret = client.get_secret_value(SecretId="/one-system/db/credentials")
            creds = json.loads(secret["SecretString"])
            user = creds.get("username", user)
            password = creds.get("password", "")
        except Exception as exc:
            logger.error("Failed to retrieve DB credentials from Secrets Manager: %s", exc)
            sys.exit(1)

    if not host:
        logger.error("DB_HOST is not set. Run 'cdk deploy --all' and update your .env file.")
        sys.exit(1)

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
        sslmode="require",
    )


def run_seeds() -> None:
    conn = _get_connection()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        for filename in SEED_FILES:
            filepath = SEEDS_DIR / filename
            sql = filepath.read_text(encoding="utf-8")
            logger.info("Running seed: %s", filename)
            cur.execute(sql)

        conn.commit()
        logger.info("All seeds committed successfully.")
    except Exception:
        conn.rollback()
        logger.exception("Seed failed — transaction rolled back.")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def verify() -> None:
    conn = _get_connection()
    cur = conn.cursor()
    all_ok = True

    try:
        for table, (query, expected) in VERIFY_QUERIES.items():
            cur.execute(query)
            count = cur.fetchone()[0]
            status = "OK" if count >= expected else "FAIL"
            if status == "FAIL":
                all_ok = False
            logger.info("  %-25s %s  (got %d, expected >= %d)", table, status, count, expected)
    finally:
        cur.close()
        conn.close()

    if not all_ok:
        logger.error("Verification failed — some tables have fewer rows than expected.")
        sys.exit(1)

    logger.info("Verification passed.")


if __name__ == "__main__":
    logger.info("Environment: %s", ENVIRONMENT)
    logger.info("--- Running seeds ---")
    run_seeds()
    logger.info("--- Verifying row counts ---")
    verify()
