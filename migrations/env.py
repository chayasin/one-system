"""
Alembic env.py — connects to Aurora via environment variables or Secrets Manager.

Priority order for DB credentials:
  1. LOCAL_DB_* variables  (when ENVIRONMENT=development)
  2. DB_HOST + DB_PASSWORD env vars (set after cdk deploy outputs)
  3. AWS Secrets Manager at /one-system/db/credentials (production)

Usage:
  # Development (local Docker Compose):
  ENVIRONMENT=development alembic upgrade head

  # Production (against Aurora, credentials from Secrets Manager):
  ENVIRONMENT=production alembic upgrade head
"""
import json
import logging
import os
import sys
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool, text

# ---------------------------------------------------------------------------
# Load .env from repo root
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_repo_root / ".env", override=False)

# ---------------------------------------------------------------------------
# Resolve connection URL
# ---------------------------------------------------------------------------
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")

logger = logging.getLogger("alembic.env")


def _get_db_url() -> str:
    """Return a psycopg2 connection URL based on the current environment."""
    if ENVIRONMENT == "development":
        host = os.environ.get("LOCAL_DB_HOST", "localhost")
        port = os.environ.get("LOCAL_DB_PORT", "5433")
        name = os.environ.get("LOCAL_DB_NAME", "one_system_dev")
        user = os.environ.get("LOCAL_DB_USER", "postgres")
        password = os.environ.get("LOCAL_DB_PASSWORD", "localpassword")
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    # --- Staging / Production ---
    host = os.environ.get("DB_HOST", "")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "one_system")
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")

    # Fall back to Secrets Manager if DB_HOST is set but DB_PASSWORD is empty
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
        logger.error(
            "DB_HOST is not set. Run 'cdk deploy --all' and update your .env file."
        )
        sys.exit(1)

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


# ---------------------------------------------------------------------------
# Alembic config
# ---------------------------------------------------------------------------
config = context.config
config.set_main_option("sqlalchemy.url", _get_db_url())

# Interpret the config file for Python logging
if config.config_file_name is not None:
    import logging.config
    logging.config.fileConfig(config.config_file_name)

target_metadata = None  # We use raw SQL migrations, no SQLAlchemy models here


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generate SQL script without DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
