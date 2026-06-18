"""Email alerts for dashboard download audit events."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from src.config import get_settings

logger = logging.getLogger(__name__)


def _format_person(first_name: str | None, last_name: str | None) -> str:
    parts = [p for p in ((first_name or "").strip(), (last_name or "").strip()) if p]
    return " ".join(parts) if parts else "Not provided"


def send_download_alert_email(
    *,
    dataset_label: str,
    file_name: str,
    date_range_start: str,
    date_range_end: str,
    row_count: int,
    ip_address: str | None,
    first_name: str | None,
    last_name: str | None,
    downloaded_at: str,
) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        logger.info("Download alert email skipped — SMTP not configured")
        return

    to_addr = settings.download_alert_email
    person = _format_person(first_name, last_name)
    ip_text = ip_address or "Unknown"

    subject = f"SOMA data export: {dataset_label}"
    body = f"""A CSV export was downloaded from the SOMA Studios analytics dashboard.

Dataset: {dataset_label}
File: {file_name}
Date range: {date_range_start} to {date_range_end}
Rows: {row_count:,}

Downloaded at: {downloaded_at}
IP address: {ip_text}
Name: {person}

This is an automated message from the SOMA download audit log.
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    logger.info("Download alert email sent to %s", to_addr)
