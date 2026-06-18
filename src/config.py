import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = ""
    dashboard_password: str = ""

    revolut_client_id: str = ""
    revolut_private_key_path: str = ""
    revolut_private_key: str = ""  # alternative to file (e.g. GitHub secret with \n)
    revolut_refresh_token: str = ""
    revolut_api_base: str = "https://b2b.revolut.com/api/1.0"
    revolut_webhook_secret: str = ""

    sync_lookback_days: int = 90
    revolut_initial_lookback_days: int = 365

    download_alert_email: str = "info@somastudiosmt.net"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True


def get_settings() -> Settings:
    return Settings()


def get_revolut_private_key() -> str:
    settings = get_settings()
    if settings.revolut_private_key.strip():
        return settings.revolut_private_key.replace("\\n", "\n")
    env_key = os.environ.get("REVOLUT_PRIVATE_KEY", "").strip()
    if env_key:
        return env_key.replace("\\n", "\n")
    path = Path(settings.revolut_private_key_path)
    if path.is_file():
        return path.read_text()
    raise FileNotFoundError(
        "Revolut private key not found — set REVOLUT_PRIVATE_KEY or REVOLUT_PRIVATE_KEY_PATH"
    )
