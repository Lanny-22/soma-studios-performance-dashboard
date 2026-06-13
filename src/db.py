import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from psycopg import Connection, connect
from psycopg.rows import dict_row

from src.config import get_settings


def _conninfo() -> str:
    url = get_settings().database_url
    if not url:
        raise ValueError("DATABASE_URL is not set — add it to .env before running sync jobs")
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


@contextmanager
def get_conn() -> Generator[Connection, None, None]:
    """Open one connection per use — reliable on Streamlit Cloud (no pool timeouts)."""
    conn = connect(
        _conninfo(),
        row_factory=dict_row,
        prepare_threshold=None,
        connect_timeout=20,
    )
    try:
        yield conn
    finally:
        conn.close()


def start_sync_run(source: str) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO sync_runs (source) VALUES (%s) RETURNING id",
            (source,),
        ).fetchone()
        conn.commit()
        return row["id"]


def finish_sync_run(run_id: int, status: str, records: int = 0, error: Optional[str] = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE sync_runs
            SET finished_at = %s, status = %s, records_upserted = %s, error_message = %s
            WHERE id = %s
            """,
            (datetime.now(timezone.utc), status, records, error, run_id),
        )
        conn.commit()


def webhook_already_processed(event_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM webhook_events WHERE id = %s",
            (event_id,),
        ).fetchone()
        return row is not None


def record_webhook_event(
    event_id: str,
    source: str,
    event_type: str,
    payload: Any,
    processed: bool = True,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO webhook_events (id, source, event_type, raw_payload, processed_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                event_id,
                source,
                event_type,
                json.dumps(payload),
                datetime.now(timezone.utc) if processed else None,
            ),
        )
        conn.commit()


def upsert_row(conn: Connection, table: str, id_col: str, id_val: Any, data: dict[str, Any]) -> None:
    columns = list(data.keys())
    placeholders = ", ".join(f"%({c})s" for c in columns)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != id_col)
    sql = f"""
        INSERT INTO {table} ({id_col}, {", ".join(columns)})
        VALUES (%({id_col})s, {placeholders})
        ON CONFLICT ({id_col}) DO UPDATE SET {updates}
    """
    conn.execute(sql, {id_col: id_val, **data})
