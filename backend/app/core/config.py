"""
Application settings loaded from environment variables or .env file.

Priority:
  1. Environment variables (always win)
  2. .env file in project root (local dev)
  3. Defaults

When ENVIRONMENT=production and DB credentials are not set, they are fetched
from AWS Secrets Manager at /one-system/db/credentials.

When DEV_SKIP_AUTH=true (only allowed in development), Cognito JWT verification
is bypassed and requests are authenticated via X-Dev-User-ID header.
"""
import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_repo_root = Path(__file__).resolve().parents[3]  # backend/ → project root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_repo_root / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # Runtime environment
    # ------------------------------------------------------------------ #
    environment: str = "development"

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "one_system"
    db_user: str = "postgres"
    db_password: str = ""

    # Local dev overrides (used when ENVIRONMENT=development)
    local_db_host: str = "localhost"
    local_db_port: int = 5433
    local_db_name: str = "one_system_dev"
    local_db_user: str = "postgres"
    local_db_password: str = "localpassword"

    # ------------------------------------------------------------------ #
    # AWS
    # ------------------------------------------------------------------ #
    aws_region: str = "ap-southeast-7"
    aws_account_id: str = ""

    # ------------------------------------------------------------------ #
    # Cognito
    # ------------------------------------------------------------------ #
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""

    # ------------------------------------------------------------------ #
    # S3
    # ------------------------------------------------------------------ #
    s3_attachments_bucket: str = ""
    s3_exports_bucket: str = ""
    s3_audit_bucket: str = ""
    s3_landing_bucket: str = ""

    # ------------------------------------------------------------------ #
    # SQS
    # ------------------------------------------------------------------ #
    sqs_notification_queue_url: str = ""
    sqs_export_queue_url: str = ""

    # ------------------------------------------------------------------ #
    # Dev-mode bypass (only honoured when environment == "development")
    # ------------------------------------------------------------------ #
    dev_skip_auth: bool = False

    # ------------------------------------------------------------------ #
    # JWKS cache TTL (seconds)
    # ------------------------------------------------------------------ #
    jwks_cache_ttl: int = 86400  # 24 hours

    # ------------------------------------------------------------------ #
    # Computed properties
    # ------------------------------------------------------------------ #

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def auth_disabled(self) -> bool:
        """True only when running in development with explicit opt-in."""
        return self.is_development and self.dev_skip_auth

    @property
    def cognito_configured(self) -> bool:
        return bool(self.cognito_user_pool_id and self.cognito_app_client_id)

    @property
    def database_url(self) -> str:
        """Async asyncpg URL."""
        host, port, name, user, password = self._resolve_db_credentials()
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"

    @property
    def database_url_sync(self) -> str:
        """Sync psycopg2 URL (Alembic)."""
        host, port, name, user, password = self._resolve_db_credentials()
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    def _resolve_db_credentials(self) -> tuple[str, int, str, str, str]:
        if self.is_development:
            return (
                self.local_db_host,
                self.local_db_port,
                self.local_db_name,
                self.local_db_user,
                self.local_db_password,
            )

        host = self.db_host
        password = self.db_password
        user = self.db_user

        # Pull from Secrets Manager if host set but password missing
        if host and not password:
            password, user = self._fetch_db_credentials_from_secrets_manager(user)

        if not host:
            raise RuntimeError(
                "DB_HOST is not set. Run 'cdk deploy --all' and update your .env."
            )

        return host, self.db_port, self.db_name, user, password

    def _fetch_db_credentials_from_secrets_manager(
        self, default_user: str
    ) -> tuple[str, str]:
        try:
            import boto3

            client = boto3.client("secretsmanager", region_name=self.aws_region)
            secret = client.get_secret_value(SecretId="/one-system/db/credentials")
            creds = json.loads(secret["SecretString"])
            return creds.get("password", ""), creds.get("username", default_user)
        except Exception as exc:
            logger.error("Failed to retrieve DB credentials from Secrets Manager: %s", exc)
            raise RuntimeError("Cannot connect to database: missing credentials") from exc

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v.lower()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
