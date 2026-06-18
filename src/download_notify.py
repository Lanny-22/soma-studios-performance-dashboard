"""Email alerts for dashboard download audit events."""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from src.config import get_settings

logger = logging.getLogger(__name__)


def _format_person(first_name: str | None, last_name: str | None) -> str:
    parts = [p for p in ((first_name or "").strip(), (last_name or "").strip()) if p]
    return " ".join(parts) if parts else "Not provided"


def _alert_content(
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
) -> tuple[str, str]:
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
    return subject, body


def _send_via_resend(
    *,
    to_addr: str,
    from_addr: str,
    api_key: str,
    subject: str,
    body: str,
) -> None:
    payload = json.dumps(
        {
            "from": from_addr,
            "to": [to_addr],
            "subject": subject,
            "text": body,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(f"Resend API HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API error: {detail}") from exc


def _send_via_smtp(
    *,
    to_addr: str,
    from_addr: str,
    subject: str,
    body: str,
) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


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
    to_addr = settings.download_alert_email
    subject, body = _alert_content(
        dataset_label=dataset_label,
        file_name=file_name,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        row_count=row_count,
        ip_address=ip_address,
        first_name=first_name,
        last_name=last_name,
        downloaded_at=downloaded_at,
    )

    if settings.resend_api_key.strip():
        _send_via_resend(
            to_addr=to_addr,
            from_addr=settings.resend_from,
            api_key=settings.resend_api_key.strip(),
            subject=subject,
            body=body,
        )
        logger.info("Download alert email sent via Resend to %s", to_addr)
        return

    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        _send_via_smtp(
            to_addr=to_addr,
            from_addr=settings.smtp_from or settings.smtp_user,
            subject=subject,
            body=body,
        )
        logger.info("Download alert email sent via SMTP to %s", to_addr)
        return

    logger.info("Download alert email skipped — set RESEND_API_KEY or SMTP credentials")
