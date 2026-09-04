import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GOVERNANCE_SQLITE_PATH = "data/governance.sqlite"
SERVERLESS_GOVERNANCE_SQLITE_PATH = "/tmp/rixo-governance.sqlite"
VERCEL_FUNCTION_BODY_LIMIT_BYTES = int(4.5 * 1024 * 1024)
SAFE_UPLOAD_CHUNK_BYTES = 3 * 1024 * 1024
GOVERNANCE_TICKET_HEADER = "X-Governance-Ticket"
DEFAULT_GOVERNANCE_TICKET_TTL_SECONDS = 12 * 60 * 60
MAX_GOVERNANCE_TICKET_CHARS = 6000


def is_serverless_runtime() -> bool:
    """Vercel sets VERCEL=1. AWS Lambda sets AWS_LAMBDA_FUNCTION_NAME."""
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def resolve_governance_sqlite_path(configured: str | None = None) -> str:
    """Keep the local default; relocate unwritable/relative paths on serverless."""
    path = settings.governance_sqlite_path if configured is None else str(configured)
    path = path.strip()
    if not path or path == ":memory:" or not is_serverless_runtime():
        return path
    candidate = Path(path)
    if candidate.is_absolute() and _parent_is_writable(candidate):
        return path
    return SERVERLESS_GOVERNANCE_SQLITE_PATH


def _parent_is_writable(db_path: Path) -> bool:
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".rixo-write-probe"
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Fraud-Spike Investigator"
    cors_origins: str = (
        "http://localhost:5173,https://rixo-risk-intelligence.vercel.app,https://rixo-risk-intelligence-frontend.vercel.app"
    )
    custom_max_upload_mb: int = 1024
    custom_max_rows: int = 2_000_000
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_mode: str = "test"
    governance_sqlite_path: str = DEFAULT_GOVERNANCE_SQLITE_PATH
    governance_signing_key: str = "rixo-governance-ticket-v1"
    governance_ticket_ttl_seconds: int = DEFAULT_GOVERNANCE_TICKET_TTL_SECONDS

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
