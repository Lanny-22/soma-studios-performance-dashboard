"""Import Momence CSV exports from imports/momence/inbox/ into Supabase."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import shutil
import calendar
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from src.db import finish_sync_run, get_conn, start_sync_run, upsert_row

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "imports" / "momence" / "inbox"
IMPORTED = ROOT / "imports" / "momence" / "imported"
STUDIO_TZ = ZoneInfo("Europe/Malta")


def _norm(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def _pick(row: dict[str, str], *candidates: str) -> str | None:
    norm_map = {_norm(k): v for k, v in row.items()}
    for c in candidates:
        key = _norm(c)
        if key in norm_map and norm_map[key]:
            return str(norm_map[key]).strip()
    return None


def _parse_amount(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.,\-]", "", raw).replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%d, %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_dt_malta(raw: str | None) -> datetime | None:
    """Parse Momence CSV datetimes as studio local time (Malta), store as UTC."""
    if not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%d, %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
    ):
        try:
            local = datetime.strptime(text, fmt).replace(tzinfo=STUDIO_TZ)
            return local.astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=STUDIO_TZ).astimezone(timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row_id(row: dict[str, str], file_stem: str, prefix: str) -> str:
    explicit = _pick(row, "id", "sale id", "booking id", "member id", "session id")
    if explicit:
        return f"{prefix}-{explicit}"
    blob = json.dumps({"file": file_stem, "row": row}, sort_keys=True)
    return f"{prefix}-" + hashlib.sha256(blob.encode()).hexdigest()[:24]


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        return [row for row in reader if any(v and str(v).strip() for v in row.values())]


def _import_table(
    path: Path,
    table: str,
    id_prefix: str,
    build_fields: Callable[[dict[str, str], str], dict],
) -> int:
    rows = _read_rows(path)
    stem = path.stem
    count = 0
    with get_conn() as conn:
        for row in rows:
            row_id = _row_id(row, stem, id_prefix)
            fields = build_fields(row, path.name)
            upsert_row(conn, table, "id", row_id, fields)
            count += 1
        conn.commit()
    return count


def import_sales_csv(path: Path) -> int:
    def fields(row: dict[str, str], filename: str) -> dict:
        return {
            "source_file": filename,
            "sold_at": _parse_dt(
                _pick(row, "Sale Date", "sale date", "date", "sold at", "created at", "timestamp")
            ),
            "amount": _parse_amount(
                _pick(row, "Amount", "total", "price", "gross", "net", "paid", "revenue")
            ),
            "currency": _pick(row, "Currency", "currency") or "EUR",
            "raw_data": json.dumps(row),
            "imported_at": datetime.now(timezone.utc),
        }

    return _import_table(path, "momence_sales", "sale", fields)


def import_bookings_csv(path: Path) -> int:
    def fields(row: dict[str, str], filename: str) -> dict:
        cancelled = _pick(row, "cancelled", "cancelled at", "status")
        status = "cancelled" if cancelled and cancelled.lower() not in ("no", "false", "0") else "booked"
        return {
            "source_file": filename,
            "booked_at": _parse_dt(
                _pick(row, "Booked At", "booked at", "date", "created at", "session date", "starts at")
            ),
            "status": _pick(row, "Status", "status") or status,
            "raw_data": json.dumps(row),
            "imported_at": datetime.now(timezone.utc),
        }

    return _import_table(path, "momence_bookings", "booking", fields)


def import_members_csv(path: Path) -> int:
    def fields(row: dict[str, str], filename: str) -> dict:
        return {
            "source_file": filename,
            "email": _pick(row, "Email", "email", "e-mail"),
            "first_name": _pick(row, "First Name", "first name", "firstname"),
            "last_name": _pick(row, "Last Name", "last name", "lastname"),
            "raw_data": json.dumps(row),
            "imported_at": datetime.now(timezone.utc),
        }

    return _import_table(path, "momence_members", "member", fields)


def import_sessions_csv(path: Path) -> int:
    def fields(row: dict[str, str], filename: str) -> dict:
        return {
            "source_file": filename,
            "starts_at": _parse_dt(
                _pick(row, "Starts At", "starts at", "start", "date", "session date", "date time")
            ),
            "name": _pick(row, "Name", "name", "class", "session", "title"),
            "raw_data": json.dumps(row),
            "imported_at": datetime.now(timezone.utc),
        }

    return _import_table(path, "momence_sessions", "session", fields)


def import_total_sales_csv(path: Path) -> int:
    rows = _read_rows(path)
    count = 0
    with get_conn() as conn:
        for row in rows:
            sale_ref = _pick(row, "Sale reference", "sale reference")
            row_id = f"total-sale-{sale_ref}" if sale_ref else _row_id(row, path.stem, "total-sale")
            fields = {
                "source_file": path.name,
                "sale_reference": sale_ref,
                "category": _pick(row, "Category", "category"),
                "item": _pick(row, "Item", "item"),
                "payment_at": _parse_dt(_pick(row, "Payment date", "payment date")),
                "service_at": _parse_dt(_pick(row, "Service date", "service date")),
                "sale_value": _parse_amount(_pick(row, "Sale value", "sale value")),
                "tax": _parse_amount(_pick(row, "Tax", "tax")),
                "refunded": _parse_amount(_pick(row, "Refunded", "refunded")),
                "payment_method": _pick(row, "Payment method", "payment method"),
                "payment_status": _pick(row, "Payment status", "payment status"),
                "sold_by": _pick(row, "Sold by", "sold by"),
                "paying_customer_email": _pick(
                    row, "Paying Customer email", "paying customer email"
                ),
                "paying_customer_name": _pick(
                    row, "Paying Customer name", "paying customer name"
                ),
                "customer_email": _pick(row, "Customer email", "customer email"),
                "customer_name": _pick(row, "Customer name", "customer name"),
                "location": _pick(row, "Location", "location"),
                "note": _pick(row, "Note", "note"),
                "raw_data": json.dumps(row),
                "imported_at": datetime.now(timezone.utc),
            }
            upsert_row(conn, "momence_total_sales", "id", row_id, fields)
            count += 1
        conn.commit()
    return count


_MONTH_ABBR: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def _parse_report_month(path: Path) -> date:
    stem = path.stem.upper()
    month_num = next((n for abbr, n in _MONTH_ABBR.items() if abbr in stem), None)
    if month_num is None:
        raise ValueError(f"Cannot parse report month from {path.name}")
    year_match = re.search(r"(\d{2})$", stem)
    year = 2000 + int(year_match.group(1)) if year_match else datetime.now().year
    return date(year, month_num, 1)


def _parse_report_period(path: Path) -> tuple[date, date, date]:
    """Return (report_month, period_start, period_end) from export filename."""
    stem = re.sub(r"^\d{8}_\d{6}_", "", path.stem)
    range_match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_]+(\d{4})[-_]?(\d{2})[-_]?(\d{2})", stem)
    if range_match:
        y1, m1, d1, y2, m2, d2 = (int(range_match.group(i)) for i in range(1, 7))
        period_start = date(y1, m1, d1)
        period_end = date(y2, m2, d2)
        if period_end < period_start:
            period_start, period_end = period_end, period_start
        return period_start.replace(day=1), period_start, period_end

    month_start = _parse_report_month(path)
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start, month_start, month_start.replace(day=last_day)


def import_instructor_performance_csv(path: Path) -> int:
    rows = _read_rows(path)
    count = 0
    with get_conn() as conn:
        for row in rows:
            class_name = _pick(row, "Class Name", "class name") or ""
            class_date_raw = _pick(row, "Class Date", "class date") or ""
            location = _pick(row, "Location", "location") or ""
            first = _pick(row, "Instructor First Name", "instructor first name") or ""
            last = _pick(row, "Instructor Last Name", "instructor last name") or ""
            id_key = f"{class_date_raw}|{class_name}|{location}|{first}|{last}"
            row_id = "instr-" + hashlib.sha256(id_key.encode()).hexdigest()[:24]

            participants = _parse_int(_pick(row, "Participants", "participants"))
            checked_in = _parse_int(_pick(row, "Checked in", "checked in"))
            comps = _parse_int(_pick(row, "Comps", "comps"))
            checked_in_comps = _parse_int(_pick(row, "Checked In Comps", "checked in comps"))
            late_cancellations = _parse_int(
                _pick(row, "Late Cancellations", "late cancellations")
            )
            non_paid = _parse_int(_pick(row, "Non Paid Customers", "non paid customers"))
            hours = _parse_amount(_pick(row, "Time (h)", "time h", "total time (h)"))

            fields = {
                "source_file": path.name,
                "class_name": class_name,
                "class_at": _parse_dt_malta(class_date_raw),
                "location": location,
                "payrate": _pick(row, "Payrate", "payrate"),
                "total_revenue": _parse_amount(_pick(row, "Total Revenue", "total revenue")),
                "base_payout": _parse_amount(_pick(row, "Base Payout", "base payout")),
                "additional_payout": _parse_amount(
                    _pick(row, "Additional Payout", "additional payout")
                ),
                "total_payout": _parse_amount(_pick(row, "Total Payout", "total payout")),
                "tip": _parse_amount(_pick(row, "Tip", "tip")),
                "participants": participants,
                "checked_in": checked_in,
                "comps": comps,
                "checked_in_comps": checked_in_comps,
                "late_cancellations": late_cancellations,
                "non_paid_customers": non_paid,
                "hours": hours,
                "instructor_first_name": first,
                "instructor_last_name": last,
                "employee_code": _pick(row, "Employee Code", "employee code"),
                "payrate_code": _pick(row, "Payrate Code", "payrate code"),
                "raw_data": json.dumps(row),
                "imported_at": datetime.now(timezone.utc),
            }
            upsert_row(conn, "momence_instructor_performance", "id", row_id, fields)
            count += 1
        conn.commit()
    return count


def _parse_int(raw: str | None) -> int | None:
    amount = _parse_amount(raw)
    if amount is None:
        return None
    return int(amount)


def import_class_occupancy_csv(path: Path) -> int:
    rows = _read_rows(path)
    count = 0
    with get_conn() as conn:
        for row in rows:
            date_raw = _pick(row, "Date", "date") or ""
            class_name = _pick(row, "Class Name", "class name") or ""
            location = _pick(row, "Location", "location") or ""
            instructor = _pick(row, "Instructor Name", "instructor name") or ""
            id_key = f"{date_raw}|{class_name}|{location}|{instructor}"
            row_id = "occupancy-" + hashlib.sha256(id_key.encode()).hexdigest()[:24]
            capacity = _parse_int(_pick(row, "Capacity", "capacity"))
            bookings = _parse_int(_pick(row, "Bookings", "bookings"))
            check_ins = _parse_int(_pick(row, "Check-Ins", "check-ins", "check ins"))
            no_shows = _parse_int(_pick(row, "No Shows", "no shows"))
            late_cancellations = _parse_int(
                _pick(row, "Late Cancellations", "late cancellations")
            )
            occupancy = _parse_amount(_pick(row, "Occupancy %", "occupancy"))
            fields = {
                "source_file": path.name,
                "class_name": _pick(row, "Class Name", "class name"),
                "class_at": _parse_dt_malta(_pick(row, "Date", "date")),
                "instructor_name": _pick(row, "Instructor Name", "instructor name"),
                "location": _pick(row, "Location", "location"),
                "capacity": capacity,
                "bookings": bookings,
                "check_ins": check_ins,
                "no_shows": no_shows,
                "late_cancellations": late_cancellations,
                "occupancy_pct": occupancy,
                "raw_data": json.dumps(row),
                "imported_at": datetime.now(timezone.utc),
            }
            upsert_row(conn, "momence_class_occupancy", "id", row_id, fields)
            count += 1
        conn.commit()
    return count


def _is_presale_membership(name: str) -> bool:
    """Presale 3-credit packs (PRE-SALE offer + 3 Credit PreSale template)."""
    lower = name.lower()
    return "pre-sale" in lower or "presale" in lower


def _snapshot_date_from_filename(path: Path) -> date:
    match = re.search(r"(\d{4})(\d{2})(\d{2})", path.stem)
    if not match:
        raise ValueError(f"Cannot parse snapshot date from {path.name}")
    y, m, d = (int(match.group(i)) for i in range(1, 4))
    return date(y, m, d)


def import_active_members_csv(path: Path) -> int:
    rows = _read_rows(path)
    snapshot_date = _snapshot_date_from_filename(path)
    count = 0
    with get_conn() as conn:
        for row in rows:
            membership = _pick(row, "Membership", "membership") or ""
            if not membership.strip():
                continue
            row_id = hashlib.sha256(
                f"{snapshot_date.isoformat()}|{membership}".encode()
            ).hexdigest()[:32]
            fields = {
                "source_file": path.name,
                "snapshot_date": snapshot_date,
                "membership": membership.strip(),
                "membership_type": _pick(row, "Type", "type"),
                "avg_usage": _parse_amount(_pick(row, "Avg. usage", "avg usage", "Avg usage")),
                "active_count": int(_parse_amount(_pick(row, "Active", "active")) or 0),
                "is_presale": _is_presale_membership(membership),
                "raw_data": json.dumps(row),
                "imported_at": datetime.now(timezone.utc),
            }
            upsert_row(conn, "momence_active_members", "id", row_id, fields)
            count += 1
        conn.commit()
    return count


FOLDER_IMPORTERS: dict[str, tuple[str, Callable[[Path], int]]] = {
    "totalsales": ("momence_total_sales", import_total_sales_csv),
    "instructorperformance": (
        "momence_instructor_performance",
        import_instructor_performance_csv,
    ),
    "classoccupancy": ("momence_class_occupancy", import_class_occupancy_csv),
    "activemembers": ("momence_active_members", import_active_members_csv),
}


def _inbox_folder_key(path: Path) -> str | None:
    try:
        rel = path.relative_to(INBOX)
    except ValueError:
        return None
    if len(rel.parts) < 2:
        return None
    return _norm(rel.parts[0])


def _target_for_path(path: Path) -> tuple[str, Callable[[Path], int]]:
    folder_key = _inbox_folder_key(path)
    if folder_key and folder_key in FOLDER_IMPORTERS:
        return FOLDER_IMPORTERS[folder_key]
    return _target_for_filename(path.name)


def _target_for_filename(name: str) -> tuple[str, Callable[[Path], int]]:
    lower = name.lower()
    if "booking" in lower or "attendance" in lower:
        return "momence_bookings", import_bookings_csv
    if "member" in lower and "sales" not in lower:
        return "momence_members", import_members_csv
    if "session" in lower or "class" in lower or "schedule" in lower:
        return "momence_sessions", import_sessions_csv
    return "momence_sales", import_sales_csv


def _already_imported(file_hash: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM csv_import_log WHERE file_hash = %s",
            (file_hash,),
        ).fetchone()
        return row is not None


def _record_import(file_hash: str, filename: str, target_table: str, rows: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO csv_import_log (file_hash, filename, target_table, rows_imported)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (file_hash) DO UPDATE SET
                rows_imported = EXCLUDED.rows_imported,
                imported_at = now()
            """,
            (file_hash, filename, target_table, rows),
        )
        conn.commit()


def _archive_file(path: Path) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    try:
        rel_parent = path.relative_to(INBOX).parent
    except ValueError:
        rel_parent = Path()
    dest_dir = IMPORTED / rel_parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{stamp}_{path.name}"
    shutil.move(str(path), str(dest))
    logger.info("Archived %s → %s", path.name, dest)


def process_inbox() -> dict[str, int]:
    INBOX.mkdir(parents=True, exist_ok=True)
    IMPORTED.mkdir(parents=True, exist_ok=True)

    results: dict[str, int] = {}
    files = sorted(INBOX.glob("**/*.csv"))
    if not files:
        logger.info("CSV inbox empty (%s)", INBOX)
        return results

    for path in files:
        digest = _file_hash(path)
        rel_name = str(path.relative_to(INBOX))
        if _already_imported(digest):
            logger.info("Skipping %s (already imported)", rel_name)
            _archive_file(path)
            continue

        table, importer = _target_for_path(path)
        try:
            rows = importer(path)
            _record_import(digest, rel_name, table, rows)
            _archive_file(path)
            results[rel_name] = rows
            logger.info("Imported %s → %s (%d rows)", rel_name, table, rows)
        except Exception:
            logger.exception("Failed to import %s — left in inbox", rel_name)

    return results


def run_csv_import() -> dict[str, int]:
    run_id = start_sync_run("momence_csv")
    try:
        results = process_inbox()
        total = sum(results.values())
        finish_sync_run(run_id, "success", total)
        return results
    except Exception as exc:
        finish_sync_run(run_id, "failed", 0, str(exc))
        raise
