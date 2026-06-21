"""Load Momence sales data from Supabase for the analytics dashboard."""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timezone

import pandas as pd

from src.db import get_conn
logger = logging.getLogger(__name__)

STUDIO_TIMEZONE = "Europe/Malta"
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def format_studio_hour_label(hour: int) -> str:
    """Malta local hour bucket label for charts (e.g. 6 -> '6:00 AM', 19 -> '7:00 PM')."""
    suffix = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    return f"{hour_12}:00 {suffix}"

SALES_QUERY = """
    SELECT
        payment_at,
        service_at,
        sale_value,
        refunded,
        category,
        item,
        sale_reference
    FROM momence_total_sales
    WHERE payment_at IS NOT NULL
    ORDER BY payment_at
"""


def load_total_sales() -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(SALES_QUERY).fetchall()
    df = pd.DataFrame(rows)

    df["payment_at"] = pd.to_datetime(df["payment_at"], utc=True)
    df["service_at"] = pd.to_datetime(df["service_at"], utc=True, errors="coerce")
    df["sale_date"] = df["payment_at"].dt.date
    df["service_date"] = pd.Series([pd.NaT] * len(df), dtype="object")
    df["service_hour"] = pd.array([pd.NA] * len(df), dtype="Int64")
    df["service_day"] = pd.Series([None] * len(df), dtype="object")
    valid_service = df["service_at"].notna()
    if valid_service.any():
        service_local = df.loc[valid_service, "service_at"].dt.tz_convert(STUDIO_TIMEZONE)
        df.loc[valid_service, "service_date"] = service_local.dt.date
        df.loc[valid_service, "service_hour"] = service_local.dt.hour.astype("Int64")
        df.loc[valid_service, "service_day"] = service_local.dt.day_name()
    df["sale_value"] = pd.to_numeric(df["sale_value"], errors="coerce").fillna(0)
    df["refunded"] = pd.to_numeric(df["refunded"], errors="coerce").fillna(0)
    df["net_sales"] = df["sale_value"] - df["refunded"]
    df["category"] = df["category"].fillna("Unknown")
    return df


CLASS_OCCUPANCY_QUERY = """
    SELECT
        class_name,
        class_at,
        instructor_name,
        location,
        capacity,
        bookings,
        check_ins,
        no_shows,
        late_cancellations,
        occupancy_pct
    FROM momence_class_occupancy
    WHERE class_at IS NOT NULL
    ORDER BY class_at
"""


def load_class_occupancy() -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(CLASS_OCCUPANCY_QUERY).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["class_at"] = pd.to_datetime(df["class_at"], utc=True)
    local = df["class_at"].dt.tz_convert(STUDIO_TIMEZONE)
    df["class_date"] = local.dt.date
    df["class_hour"] = local.dt.hour.astype("Int64")
    df["class_day"] = local.dt.day_name()
    df["class_time"] = local.dt.strftime("%H:%M")
    for col in ("capacity", "bookings", "check_ins", "no_shows", "late_cancellations"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["occupancy_pct"] = pd.to_numeric(df["occupancy_pct"], errors="coerce").fillna(0)
    return df


def filter_class_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["class_date"] >= start) & (df["class_date"] <= end)].copy()


def _occupancy_agg(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return df.groupby(["class_day", "class_hour"], as_index=False).agg(
        avg_occupancy=("occupancy_pct", "mean"),
        total_bookings=("bookings", "sum"),
        total_check_ins=("check_ins", "sum"),
        class_sessions=("class_at", "count"),
    )


def occupancy_timing_matrix(df: pd.DataFrame) -> pd.DataFrame:
    matrix = _occupancy_agg(df)
    if matrix.empty:
        return matrix
    matrix["class_hour"] = matrix["class_hour"].astype(int)
    return matrix


def occupancy_day_totals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    totals = df.groupby("class_day", as_index=False).agg(
        avg_occupancy=("occupancy_pct", "mean"),
        total_bookings=("bookings", "sum"),
        total_check_ins=("check_ins", "sum"),
        class_sessions=("class_at", "count"),
    )
    totals["class_day"] = pd.Categorical(totals["class_day"], categories=DAY_ORDER, ordered=True)
    return totals.sort_values("class_day")


def occupancy_hour_totals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    totals = (
        df.groupby("class_hour", as_index=False)
        .agg(
            avg_occupancy=("occupancy_pct", "mean"),
            total_bookings=("bookings", "sum"),
            total_check_ins=("check_ins", "sum"),
            class_sessions=("class_at", "count"),
        )
        .sort_values("class_hour")
    )
    totals["class_hour"] = totals["class_hour"].astype(int)
    return totals


def _with_per_class_metrics(grouped: pd.DataFrame) -> pd.DataFrame:
    grouped = grouped.copy()
    sessions = grouped["class_sessions"].replace(0, pd.NA)
    grouped["revenue_per_class"] = (grouped["net_sales"] / sessions).fillna(0)
    grouped["utilization_per_class"] = (grouped["transactions"] / sessions).fillna(0)
    return grouped


def filter_service_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    has_service = df["service_at"].notna()
    in_range = (df["service_date"] >= start) & (df["service_date"] <= end)
    return df.loc[has_service & in_range].copy()


def schedule_timing_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Net sales by day-of-week and hour; class_sessions = distinct service times."""
    if df.empty:
        return pd.DataFrame()

    matrix = df.groupby(["service_day", "service_hour"], as_index=False).agg(
        net_sales=("net_sales", "sum"),
        transactions=("sale_reference", "count"),
        class_sessions=("service_at", "nunique"),
    )
    matrix["service_hour"] = matrix["service_hour"].astype(int)
    return _with_per_class_metrics(matrix)


def day_of_week_totals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    totals = df.groupby("service_day", as_index=False).agg(
        net_sales=("net_sales", "sum"),
        transactions=("sale_reference", "count"),
        class_sessions=("service_at", "nunique"),
    )
    totals["service_day"] = pd.Categorical(totals["service_day"], categories=DAY_ORDER, ordered=True)
    return _with_per_class_metrics(totals.sort_values("service_day"))


def hour_totals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    totals = (
        df.groupby("service_hour", as_index=False)
        .agg(
            net_sales=("net_sales", "sum"),
            transactions=("sale_reference", "count"),
            class_sessions=("service_at", "nunique"),
        )
        .sort_values("service_hour")
    )
    totals["service_hour"] = totals["service_hour"].astype(int)
    return _with_per_class_metrics(totals)


def filter_sales(
    df: pd.DataFrame,
    categories: list[str],
    start: date,
    end: date,
) -> pd.DataFrame:
    filtered = df.copy()

    if categories:
        filtered = filtered[filtered["category"].isin(categories)]

    filtered = filtered[(filtered["sale_date"] >= start) & (filtered["sale_date"] <= end)]
    return filtered


def daily_totals(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.groupby("sale_date", as_index=False)
        .agg(net_sales=("net_sales", "sum"), transactions=("sale_reference", "count"))
        .sort_values("sale_date")
    )
    daily["cumulative_sales"] = daily["net_sales"].cumsum()
    return daily


def item_breakdown(df: pd.DataFrame, categories: list[str]) -> pd.DataFrame:
    subset = df[df["category"].isin(categories)].copy()
    if subset.empty:
        return pd.DataFrame(columns=["category", "item", "net_sales", "sales_count"])

    breakdown = (
        subset.groupby(["category", "item"], as_index=False)
        .agg(net_sales=("net_sales", "sum"), sales_count=("sale_reference", "count"))
        .sort_values("net_sales", ascending=False)
    )
    return breakdown


INSTRUCTOR_QUERY = """
    SELECT
        class_name,
        class_at,
        location,
        payrate,
        total_revenue,
        base_payout,
        additional_payout,
        total_payout,
        tip,
        participants,
        checked_in,
        comps,
        checked_in_comps,
        late_cancellations,
        non_paid_customers,
        hours,
        instructor_first_name,
        instructor_last_name
    FROM momence_instructor_performance
    WHERE class_at IS NOT NULL
    ORDER BY class_at
"""


def load_instructor_performance() -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(INSTRUCTOR_QUERY).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["class_at"] = pd.to_datetime(df["class_at"], utc=True)
    local = df["class_at"].dt.tz_convert(STUDIO_TIMEZONE)
    df["class_date"] = local.dt.date
    df["class_month"] = local.map(lambda ts: date(ts.year, ts.month, 1))

    money_cols = (
        "total_revenue",
        "base_payout",
        "additional_payout",
        "total_payout",
        "tip",
        "hours",
    )
    for col in money_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in (
        "participants",
        "checked_in",
        "comps",
        "checked_in_comps",
        "late_cancellations",
        "non_paid_customers",
    ):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["instructor_name"] = (
        df["instructor_first_name"].fillna("").astype(str).str.strip()
        + " "
        + df["instructor_last_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    df["gross_revenue"] = df["total_revenue"]
    df["instructor_payout"] = df["total_payout"]
    df["total_bookings"] = df["participants"]
    df["class_count"] = 1
    df["total_hours"] = df["hours"]
    df["studio_net"] = df["gross_revenue"] - df["instructor_payout"]
    participants = df["participants"].replace(0, pd.NA)
    df["average_attendance"] = (df["checked_in"] / participants).fillna(0)
    return df


def filter_instructor_performance(
    df: pd.DataFrame,
    start: date,
    end: date,
) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["class_date"] >= start) & (df["class_date"] <= end)].copy()


def aggregate_instructors(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    weighted = df.assign(
        att_weight=df["average_attendance"] * df["total_bookings"]
    ).groupby("instructor_name", as_index=False).agg(
        att_weight=("att_weight", "sum"),
        total_bookings=("total_bookings", "sum"),
        gross_revenue=("gross_revenue", "sum"),
        instructor_payout=("instructor_payout", "sum"),
        class_count=("class_count", "sum"),
        total_hours=("total_hours", "sum"),
    )
    weighted["average_attendance"] = weighted["att_weight"] / weighted["total_bookings"].replace(
        0, pd.NA
    )
    weighted["studio_net"] = weighted["gross_revenue"] - weighted["instructor_payout"]
    weighted["margin_pct"] = (
        weighted["studio_net"] / weighted["gross_revenue"].replace(0, pd.NA) * 100
    ).fillna(0)
    weighted["net_revenue_per_class"] = (
        weighted["studio_net"] / weighted["class_count"].replace(0, pd.NA)
    ).fillna(0)
    return weighted.drop(columns=["att_weight"]).sort_values(
        "total_bookings", ascending=False
    )


def instructor_month_comparison(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Wide instructor table with one column per calendar month in range."""
    filtered = filter_instructor_performance(df, start, end)
    if filtered.empty:
        return pd.DataFrame()

    rows = filtered.copy()
    rows["month_label"] = pd.to_datetime(rows["class_month"]).dt.strftime("%b %Y")
    month_order = (
        rows[["class_month", "month_label"]]
        .drop_duplicates()
        .sort_values("class_month")["month_label"]
        .tolist()
    )

    records: list[dict] = []
    for name, group in rows.groupby("instructor_name"):
        record: dict = {"instructor_name": name}
        for month_label in month_order:
            month_rows = group[group["month_label"] == month_label]
            if month_rows.empty:
                record[f"classes_{month_label}"] = None
                record[f"attendance_{month_label}"] = None
                record[f"net_per_class_{month_label}"] = None
                record[f"studio_net_{month_label}"] = None
                continue
            classes = len(month_rows)
            bookings = int(month_rows["total_bookings"].sum())
            att = (
                (month_rows["average_attendance"] * month_rows["total_bookings"]).sum() / bookings
                if bookings > 0
                else 0
            )
            studio_net = float(month_rows["studio_net"].sum())
            record[f"classes_{month_label}"] = classes
            record[f"attendance_{month_label}"] = att
            record[f"net_per_class_{month_label}"] = studio_net / classes if classes else 0
            record[f"studio_net_{month_label}"] = studio_net
        records.append(record)

    wide = pd.DataFrame(records)
    if not wide.empty and len(month_order) >= 2:
        first, last = month_order[0], month_order[-1]
        c0 = f"classes_{first}"
        c1 = f"classes_{last}"
        if c0 in wide.columns and c1 in wide.columns:
            wide["classes_change"] = wide[c1] - wide[c0]
        n0 = f"net_per_class_{first}"
        n1 = f"net_per_class_{last}"
        if n0 in wide.columns and n1 in wide.columns:
            wide["net_per_class_change"] = wide[n1] - wide[n0]

    sort_col = f"studio_net_{month_order[-1]}" if month_order else None
    if sort_col and sort_col in wide.columns:
        wide = wide.sort_values(sort_col, ascending=False, na_position="last")
    return wide


EXPENSES_QUERY = """
    SELECT
        id,
        completed_at,
        label,
        description,
        amount,
        fee,
        currency,
        type,
        product,
        import_notes,
        dashboard_notes,
        manually_excluded
    FROM revolut_expenses
    WHERE completed_at IS NOT NULL
      AND COALESCE(manually_excluded, FALSE) = FALSE
    ORDER BY completed_at
"""

EXPENSES_ALL_QUERY = """
    SELECT
        id,
        completed_at,
        label,
        description,
        amount,
        fee,
        currency,
        type,
        product,
        import_notes,
        dashboard_notes,
        manually_excluded
    FROM revolut_expenses
    WHERE completed_at IS NOT NULL
    ORDER BY completed_at
"""


def _prepare_expenses_df(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["completed_at"] = pd.to_datetime(df["completed_at"], utc=True)
    completed_local = df["completed_at"].dt.tz_convert(STUDIO_TIMEZONE)
    df["expense_date"] = completed_local.dt.date
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["fee"] = pd.to_numeric(df["fee"], errors="coerce").fillna(0)
    df["spend"] = df["amount"].abs()
    df["label"] = df["label"].fillna("Unknown")
    df["manually_excluded"] = df["manually_excluded"].fillna(False).astype(bool)
    for col in ("import_notes", "dashboard_notes"):
        if col in df.columns:
            df[col] = df[col].fillna("")
    return df


def load_revolut_expenses(include_excluded: bool = False) -> pd.DataFrame:
    query = EXPENSES_ALL_QUERY if include_excluded else EXPENSES_QUERY
    with get_conn() as conn:
        rows = conn.execute(query).fetchall()
    return _prepare_expenses_df(rows)


def set_expense_manually_excluded(expense_id: str, excluded: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE revolut_expenses SET manually_excluded = %s WHERE id = %s",
            (excluded, expense_id),
        )
        conn.commit()


def set_expense_dashboard_notes(expense_id: str, notes: str | None) -> None:
    """Persist studio notes on the ledger row and mirrored expense row."""
    normalized = (notes or "").strip() or None
    with get_conn() as conn:
        conn.execute(
            "UPDATE revolut_transactions SET dashboard_notes = %s WHERE id = %s",
            (normalized, expense_id),
        )
        conn.execute(
            "UPDATE revolut_expenses SET dashboard_notes = %s WHERE id = %s",
            (normalized, expense_id),
        )
        conn.commit()


def filter_expense_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["expense_date"] >= start) & (df["expense_date"] <= end)].copy()


def expense_totals_by_label(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["label", "transaction_count", "total_spend"])

    totals = (
        df.groupby("label", as_index=False)
        .agg(transaction_count=("id", "count"), total_spend=("spend", "sum"))
        .sort_values("total_spend", ascending=False)
    )
    return totals


TOTAL_SALES_EXPORT_QUERY = """
    SELECT
        sale_reference,
        category,
        item,
        payment_at,
        service_at,
        sale_value,
        tax,
        refunded,
        payment_method,
        payment_status,
        sold_by,
        paying_customer_email,
        paying_customer_name,
        customer_email,
        customer_name,
        location,
        note
    FROM momence_total_sales
    WHERE payment_at IS NOT NULL
    ORDER BY payment_at
"""

DOWNLOAD_DATASETS: dict[str, dict[str, str]] = {
    "total_sales": {
        "label": "Total Sales (Momence)",
        "description": "Momence total sales report — filtered by payment date (Malta time).",
        "file_prefix": "soma_total_sales",
    },
    "expenses": {
        "label": "Expenses (Revolut)",
        "description": "Revolut expense rows — filtered by completed date (Malta time). Includes manually excluded flag.",
        "file_prefix": "soma_expenses",
    },
    "instructor_performance": {
        "label": "Instructor Performance",
        "description": "Momence instructor pay by class session — filtered by class date (Malta time).",
        "file_prefix": "soma_instructor_performance",
    },
    "class_occupancy": {
        "label": "Class Occupancy (Momence)",
        "description": "Momence class occupancy report — filtered by class date and time (Malta).",
        "file_prefix": "soma_class_occupancy",
    },
}


def load_total_sales_export() -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(TOTAL_SALES_EXPORT_QUERY).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["payment_at"] = pd.to_datetime(df["payment_at"], utc=True)
    df["service_at"] = pd.to_datetime(df["service_at"], utc=True, errors="coerce")
    payment_local = df["payment_at"].dt.tz_convert(STUDIO_TIMEZONE)
    df["payment_date"] = payment_local.dt.date
    if df["service_at"].notna().any():
        service_local = df["service_at"].dt.tz_convert(STUDIO_TIMEZONE)
        df["service_date"] = service_local.dt.date
    else:
        df["service_date"] = None
    df["sale_value"] = pd.to_numeric(df["sale_value"], errors="coerce").fillna(0)
    df["tax"] = pd.to_numeric(df["tax"], errors="coerce").fillna(0)
    df["refunded"] = pd.to_numeric(df["refunded"], errors="coerce").fillna(0)
    df["net_sales"] = df["sale_value"] - df["refunded"]
    return df


def filter_sales_payment_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    return df[(df["payment_date"] >= start) & (df["payment_date"] <= end)].copy()


def combined_download_date_bounds(
    sales: pd.DataFrame | None = None,
    expenses: pd.DataFrame | None = None,
    instructors: pd.DataFrame | None = None,
    occupancy: pd.DataFrame | None = None,
) -> tuple[date, date]:
    bounds: list[date] = []
    if sales is not None and not sales.empty and "payment_date" in sales.columns:
        bounds.extend([sales["payment_date"].min(), sales["payment_date"].max()])
    if expenses is not None and not expenses.empty:
        bounds.extend([expenses["expense_date"].min(), expenses["expense_date"].max()])
    if instructors is not None and not instructors.empty:
        bounds.extend([instructors["class_date"].min(), instructors["class_date"].max()])
    if occupancy is not None and not occupancy.empty:
        bounds.extend([occupancy["class_date"].min(), occupancy["class_date"].max()])
    if not bounds:
        today = date.today()
        return today, today
    return min(bounds), max(bounds)


def _format_datetimes_for_csv(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        series = pd.to_datetime(out[col], utc=True, errors="coerce")
        out[col] = series.dt.tz_convert(STUDIO_TIMEZONE).dt.strftime("%Y-%m-%d %H:%M")
    return out


def build_download_export(
    dataset_key: str,
    start: date,
    end: date,
    sales_export: pd.DataFrame | None = None,
    expenses_all: pd.DataFrame | None = None,
    instructors: pd.DataFrame | None = None,
    occupancy: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if dataset_key == "total_sales":
        if sales_export is None or sales_export.empty:
            return pd.DataFrame()
        filtered = filter_sales_payment_date_range(sales_export, start, end)
        filtered = _format_datetimes_for_csv(filtered, ["payment_at", "service_at"])
        return filtered[
            [
                "sale_reference",
                "category",
                "item",
                "payment_at",
                "payment_date",
                "service_at",
                "service_date",
                "sale_value",
                "tax",
                "refunded",
                "net_sales",
                "payment_method",
                "payment_status",
                "sold_by",
                "paying_customer_email",
                "paying_customer_name",
                "customer_email",
                "customer_name",
                "location",
                "note",
            ]
        ]

    if dataset_key == "expenses":
        if expenses_all is None or expenses_all.empty:
            return pd.DataFrame()
        filtered = filter_expense_date_range(expenses_all, start, end)
        filtered = _format_datetimes_for_csv(filtered, ["completed_at"])
        return filtered[
            [
                "id",
                "completed_at",
                "expense_date",
                "label",
                "description",
                "type",
                "product",
                "amount",
                "fee",
                "spend",
                "currency",
                "import_notes",
                "dashboard_notes",
                "manually_excluded",
            ]
        ]

    if dataset_key == "instructor_performance":
        if instructors is None or instructors.empty:
            return pd.DataFrame()
        filtered = filter_instructor_performance(instructors, start, end)
        filtered = _format_datetimes_for_csv(filtered, ["class_at"])
        return filtered[
            [
                "class_name",
                "class_at",
                "class_date",
                "instructor_name",
                "location",
                "payrate",
                "total_revenue",
                "base_payout",
                "additional_payout",
                "total_payout",
                "tip",
                "participants",
                "checked_in",
                "late_cancellations",
                "hours",
            ]
        ].sort_values(["class_date", "instructor_name", "class_at"])

    if dataset_key == "class_occupancy":
        if occupancy is None or occupancy.empty:
            return pd.DataFrame()
        filtered = filter_class_date_range(occupancy, start, end)
        filtered = _format_datetimes_for_csv(filtered, ["class_at"])
        return filtered[
            [
                "class_name",
                "class_at",
                "class_date",
                "class_time",
                "instructor_name",
                "location",
                "capacity",
                "bookings",
                "check_ins",
                "no_shows",
                "late_cancellations",
                "occupancy_pct",
            ]
        ].sort_values(["class_date", "class_at"])

    return pd.DataFrame()


def log_download_event(
    *,
    dataset_key: str,
    dataset_label: str,
    file_name: str,
    date_range_start: date,
    date_range_end: date,
    row_count: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> None:
    """Insert audit row into download_log. Email alerts are disabled (deferred)."""
    downloaded_at = datetime.now(timezone.utc)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO download_log (
                downloaded_at,
                ip_address,
                user_agent,
                first_name,
                last_name,
                dataset_key,
                dataset_label,
                file_name,
                date_range_start,
                date_range_end,
                row_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                downloaded_at,
                ip_address,
                user_agent,
                (first_name or "").strip() or None,
                (last_name or "").strip() or None,
                dataset_key,
                dataset_label,
                file_name,
                date_range_start,
                date_range_end,
                row_count,
            ),
        )
        conn.commit()

    return None


# Momence categories counted as operating revenue (class, membership, retail).
BUDGET_REVENUE_CATEGORIES = ("Class", "Subscription", "Pack", "Product")

FINANCIAL_MODEL_BUDGET_QUERY = """
    SELECT
        p.period_code,
        p.period_label,
        p.period_start,
        p.period_end,
        p.period_index,
        r.class_membership_revenue,
        r.inventory_revenue,
        r.total_revenue,
        s.instructor_fees,
        s.gross_profit,
        s.gross_margin_pct,
        s.total_fixed_opex,
        s.ebitda,
        s.ebitda_margin_pct
    FROM financial_model_periods p
    JOIN financial_model_revenue r ON r.period_code = p.period_code
    JOIN financial_model_summary s ON s.period_code = p.period_code
    ORDER BY p.period_index
"""


def load_financial_model_budget() -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(FINANCIAL_MODEL_BUDGET_QUERY).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in (
        "class_membership_revenue",
        "inventory_revenue",
        "total_revenue",
        "instructor_fees",
        "gross_profit",
        "gross_margin_pct",
        "total_fixed_opex",
        "ebitda",
        "ebitda_margin_pct",
    ):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["period_start"] = pd.to_datetime(df["period_start"]).dt.date
    df["period_end"] = pd.to_datetime(df["period_end"]).dt.date
    return df


def enrich_budget_periods(budget: pd.DataFrame) -> pd.DataFrame:
    df = budget.sort_values("period_index").copy()
    df["period_range"] = df.apply(
        lambda row: f"{row['period_start']:%d %b %Y} – {row['period_end']:%d %b %Y}",
        axis=1,
    )
    return df


def build_budget_model_variable(budget: pd.DataFrame) -> pd.DataFrame:
    df = enrich_budget_periods(budget)
    return df.rename(
        columns={
            "total_revenue": "budget_revenue",
            "instructor_fees": "budget_instructor_fees",
            "gross_profit": "budget_gross_profit",
            "gross_margin_pct": "budget_gross_margin_pct",
        }
    )


def add_budget_model_cumulative(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.sort_values("period_index").copy()
    out["cum_budget_revenue"] = out["budget_revenue"].cumsum()
    out["cum_budget_instructor_fees"] = out["budget_instructor_fees"].cumsum()
    out["cum_budget_gross_profit"] = out["budget_gross_profit"].cumsum()
    out["cum_budget_gross_margin_pct"] = (
        out["cum_budget_gross_profit"] / out["cum_budget_revenue"].replace(0, pd.NA) * 100
    )
    return out


def _sales_payment_dates(df: pd.DataFrame) -> pd.Series:
    return df["payment_at"].dt.tz_convert(STUDIO_TIMEZONE).dt.date


def build_budget_vs_actuals(
    sales: pd.DataFrame,
    instructors: pd.DataFrame,
    budget: pd.DataFrame,
) -> pd.DataFrame:
    """Join financial-model periods with Momence actual revenue and instructor pay."""
    if budget.empty:
        return pd.DataFrame()

    revenue_sales = sales[sales["category"].isin(BUDGET_REVENUE_CATEGORIES)].copy()
    if not revenue_sales.empty:
        revenue_sales["payment_date"] = _sales_payment_dates(revenue_sales)

    rows: list[dict] = []
    for _, period in budget.iterrows():
        start = period["period_start"]
        end = period["period_end"]

        if revenue_sales.empty:
            actual_revenue = 0.0
        else:
            mask = (revenue_sales["payment_date"] >= start) & (
                revenue_sales["payment_date"] <= end
            )
            actual_revenue = float(revenue_sales.loc[mask, "net_sales"].sum())

        if instructors.empty:
            actual_instructor = 0.0
        else:
            inst_mask = (instructors["class_date"] >= start) & (
                instructors["class_date"] <= end
            )
            actual_instructor = float(
                instructors.loc[inst_mask, "instructor_payout"].sum()
            )

        budget_revenue = float(period["total_revenue"])
        budget_instructor = float(period["instructor_fees"])
        budget_gross_profit = float(period["gross_profit"])
        budget_margin = float(period["gross_margin_pct"])
        budget_fixed_opex = float(period["total_fixed_opex"])
        budget_net_profit = float(period["ebitda"])
        budget_net_margin = float(period["ebitda_margin_pct"])

        actual_gross_profit = actual_revenue - actual_instructor
        actual_margin = (
            (actual_gross_profit / actual_revenue * 100) if actual_revenue > 0 else None
        )

        rows.append(
            {
                "period_code": period["period_code"],
                "period_label": period["period_label"],
                "period_index": int(period["period_index"]),
                "period_start": start,
                "period_end": end,
                "period_range": f"{start:%d %b %Y} – {end:%d %b %Y}",
                "budget_revenue": budget_revenue,
                "actual_revenue": actual_revenue,
                "revenue_variance": actual_revenue - budget_revenue,
                "budget_instructor_fees": budget_instructor,
                "actual_instructor_fees": actual_instructor,
                "instructor_variance": actual_instructor - budget_instructor,
                "budget_gross_profit": budget_gross_profit,
                "actual_gross_profit": actual_gross_profit,
                "budget_gross_margin_pct": budget_margin,
                "actual_gross_margin_pct": actual_margin,
                "margin_variance_pct": (
                    actual_margin - budget_margin
                    if actual_margin is not None
                    else None
                ),
                "budget_fixed_opex": budget_fixed_opex,
                "budget_net_profit": budget_net_profit,
                "budget_net_margin_pct": budget_net_margin,
            }
        )

    return pd.DataFrame(rows)


def attach_actual_net_profit(
    comparison: pd.DataFrame,
    fixed_long: pd.DataFrame,
) -> pd.DataFrame:
    """Add actual fixed OPEX and net profit (EBITDA) from Revolut fixed expenses."""
    if comparison.empty:
        return comparison

    out = comparison.copy()
    if fixed_long.empty:
        out["actual_fixed_opex"] = 0.0
    else:
        totals = fixed_long[fixed_long["category"] == TOTAL_FIXED_EXPENSES_LABEL]
        by_code = totals.set_index("period_code")["actual_amount"]
        out["actual_fixed_opex"] = out["period_code"].map(by_code).fillna(0.0)

    out["actual_net_profit"] = out["actual_gross_profit"] - out["actual_fixed_opex"]
    out["actual_net_margin_pct"] = (
        out["actual_net_profit"] / out["actual_revenue"].replace(0, pd.NA) * 100
    )
    return out


def add_cumulative_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Running totals and cumulative gross margin by period order."""
    if df.empty:
        return df

    out = df.sort_values("period_index").copy()
    out["cum_budget_revenue"] = out["budget_revenue"].cumsum()
    out["cum_actual_revenue"] = out["actual_revenue"].cumsum()
    out["cum_revenue_variance"] = out["cum_actual_revenue"] - out["cum_budget_revenue"]
    out["cum_budget_instructor_fees"] = out["budget_instructor_fees"].cumsum()
    out["cum_actual_instructor_fees"] = out["actual_instructor_fees"].cumsum()
    out["cum_instructor_variance"] = (
        out["cum_actual_instructor_fees"] - out["cum_budget_instructor_fees"]
    )
    out["cum_budget_gross_profit"] = out["budget_gross_profit"].cumsum()
    out["cum_actual_gross_profit"] = out["actual_gross_profit"].cumsum()
    out["cum_gross_profit_variance"] = (
        out["cum_actual_gross_profit"] - out["cum_budget_gross_profit"]
    )
    out["cum_budget_gross_margin_pct"] = (
        out["cum_budget_gross_profit"] / out["cum_budget_revenue"].replace(0, pd.NA) * 100
    )
    out["cum_actual_gross_margin_pct"] = (
        out["cum_actual_gross_profit"] / out["cum_actual_revenue"].replace(0, pd.NA) * 100
    )
    out["cum_margin_variance_pct"] = (
        out["cum_actual_gross_margin_pct"] - out["cum_budget_gross_margin_pct"]
    )
    out["cum_budget_net_profit"] = out["budget_net_profit"].cumsum()
    out["cum_actual_net_profit"] = out["actual_net_profit"].cumsum()
    out["cum_net_profit_variance"] = (
        out["cum_actual_net_profit"] - out["cum_budget_net_profit"]
    )
    out["cum_budget_net_margin_pct"] = (
        out["cum_budget_net_profit"] / out["cum_budget_revenue"].replace(0, pd.NA) * 100
    )
    out["cum_actual_net_margin_pct"] = (
        out["cum_actual_net_profit"] / out["cum_actual_revenue"].replace(0, pd.NA) * 100
    )
    out["cum_net_margin_variance_pp"] = (
        out["cum_actual_net_margin_pct"] - out["cum_budget_net_margin_pct"]
    )
    return out


TOTAL_FIXED_EXPENSES_LABEL = "Total Fixed Expenses"

FIXED_COST_CATEGORY_ORDER = [
    "Rent",
    "IT Subscriptions",
    "Water & Electricity",
    "Cleaning & Maintenance",
    "Accountancy Fees",
    "Audit Fees",
    "Professional Fees",
    "Meals & Entertainment",
    "Membership & Sub Fees",
    "Telephone & Telecoms",
    "Travel Expenses",
    "Other Admin / Misc",
    "Class Materials",
    "Condominium Fees",
    "Insurance",
    "Director 1 Salary",
    "Director 2 Salary",
    "Advertising & Promotion",
]

FINANCIAL_MODEL_FIXED_EXPENSES_QUERY = """
    SELECT
        e.period_code,
        p.period_index,
        p.period_start,
        p.period_end,
        e.category,
        e.amount
    FROM financial_model_expenses e
    JOIN financial_model_periods p ON p.period_code = e.period_code
    WHERE e.expense_type = 'fixed'
    ORDER BY p.period_index, e.category
"""


def load_financial_model_fixed_expenses() -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(FINANCIAL_MODEL_FIXED_EXPENSES_QUERY).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    df["period_start"] = pd.to_datetime(df["period_start"]).dt.date
    df["period_end"] = pd.to_datetime(df["period_end"]).dt.date
    return df


def build_fixed_costs_comparison(
    expenses: pd.DataFrame,
    periods: pd.DataFrame,
) -> pd.DataFrame:
    """Long-format fixed OPEX: budget (model) vs actual (Revolut) per period and category."""
    if periods.empty:
        return pd.DataFrame()

    budget = load_financial_model_fixed_expenses()
    if budget.empty:
        return pd.DataFrame()

    expense_rows = expenses.copy()
    if not expense_rows.empty:
        expense_rows = expense_rows[~expense_rows["manually_excluded"].fillna(False)]

    rows: list[dict] = []
    for _, period in periods.sort_values("period_index").iterrows():
        start = period["period_start"]
        end = period["period_end"]
        code = period["period_code"]
        period_range = period["period_range"]
        period_index = int(period["period_index"])

        period_budget = budget[budget["period_code"] == code]
        if expense_rows.empty:
            period_actual = pd.DataFrame()
        else:
            period_actual = expense_rows[
                (expense_rows["expense_date"] >= start)
                & (expense_rows["expense_date"] <= end)
            ]

        total_budget = 0.0
        total_actual = 0.0

        for category in FIXED_COST_CATEGORY_ORDER:
            budget_rows = period_budget[period_budget["category"] == category]
            budget_amt = float(budget_rows["amount"].fillna(0).sum())

            if period_actual.empty:
                actual_amt = 0.0
            else:
                actual_amt = float(
                    period_actual.loc[period_actual["label"] == category, "spend"].sum()
                )

            total_budget += budget_amt
            total_actual += actual_amt
            rows.append(
                {
                    "period_code": code,
                    "period_index": period_index,
                    "period_range": period_range,
                    "category": category,
                    "budget_amount": budget_amt,
                    "actual_amount": actual_amt,
                }
            )

        rows.append(
            {
                "period_code": code,
                "period_index": period_index,
                "period_range": period_range,
                "category": TOTAL_FIXED_EXPENSES_LABEL,
                "budget_amount": total_budget,
                "actual_amount": total_actual,
            }
        )

    return pd.DataFrame(rows)


def build_fixed_costs_budget_long(periods: pd.DataFrame) -> pd.DataFrame:
    """Budget-only fixed OPEX from the financial model (all model periods)."""
    if periods.empty:
        return pd.DataFrame()

    budget = load_financial_model_fixed_expenses()
    if budget.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for _, period in periods.sort_values("period_index").iterrows():
        code = period["period_code"]
        period_index = int(period["period_index"])
        period_range = period["period_range"]
        period_budget = budget[budget["period_code"] == code]

        total_budget = 0.0
        for category in FIXED_COST_CATEGORY_ORDER:
            budget_rows = period_budget[period_budget["category"] == category]
            budget_amt = float(budget_rows["amount"].fillna(0).sum())
            total_budget += budget_amt
            rows.append(
                {
                    "period_code": code,
                    "period_index": period_index,
                    "period_range": period_range,
                    "category": category,
                    "budget_amount": budget_amt,
                }
            )

        rows.append(
            {
                "period_code": code,
                "period_index": period_index,
                "period_range": period_range,
                "category": TOTAL_FIXED_EXPENSES_LABEL,
                "budget_amount": total_budget,
            }
        )

    return pd.DataFrame(rows)


def add_fixed_costs_budget_cumulative(long_df: pd.DataFrame) -> pd.DataFrame:
    if long_df.empty:
        return long_df

    parts: list[pd.DataFrame] = []
    for category in long_df["category"].unique():
        part = long_df[long_df["category"] == category].sort_values("period_index").copy()
        part["cum_budget_amount"] = part["budget_amount"].cumsum()
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def add_fixed_costs_cumulative(long_df: pd.DataFrame) -> pd.DataFrame:
    if long_df.empty:
        return long_df

    parts: list[pd.DataFrame] = []
    for category in long_df["category"].unique():
        part = long_df[long_df["category"] == category].sort_values("period_index").copy()
        part["cum_budget_amount"] = part["budget_amount"].cumsum()
        part["cum_actual_amount"] = part["actual_amount"].cumsum()
        parts.append(part)
    return pd.concat(parts, ignore_index=True)
