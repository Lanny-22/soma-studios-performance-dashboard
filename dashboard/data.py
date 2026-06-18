"""Load Momence sales data from Supabase for the analytics dashboard."""

import calendar
from datetime import date

import pandas as pd

from src.db import get_conn

STUDIO_TIMEZONE = "Europe/Malta"
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

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
        report_month,
        instructor_first_name,
        instructor_last_name,
        instructor_email,
        average_attendance,
        total_bookings,
        gross_revenue,
        instructor_payout,
        class_count,
        total_hours
    FROM momence_instructor_performance
    ORDER BY report_month, instructor_last_name, instructor_first_name
"""


def load_instructor_performance() -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(INSTRUCTOR_QUERY).fetchall()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in (
        "average_attendance",
        "total_bookings",
        "gross_revenue",
        "instructor_payout",
        "class_count",
        "total_hours",
    ):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["report_month"] = pd.to_datetime(df["report_month"]).dt.date
    df["instructor_name"] = (
        df["instructor_first_name"].fillna("").astype(str).str.strip()
        + " "
        + df["instructor_last_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    df["studio_net"] = df["gross_revenue"] - df["instructor_payout"]
    return df


def filter_instructor_performance(
    df: pd.DataFrame,
    start: date,
    end: date,
) -> pd.DataFrame:
    if df.empty:
        return df

    def month_overlaps(month_start: date) -> bool:
        last_day = month_start.replace(
            day=calendar.monthrange(month_start.year, month_start.month)[1]
        )
        return month_start <= end and last_day >= start

    mask = df["report_month"].map(month_overlaps)
    return df.loc[mask].copy()


def aggregate_instructors(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    weighted = df.assign(
        att_weight=df["average_attendance"] * df["total_bookings"]
    ).groupby("instructor_name", as_index=False).agg(
        att_weight=("att_weight", "sum"),
        instructor_email=("instructor_email", "first"),
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
    """Wide instructor table with one column per report month in range."""
    filtered = filter_instructor_performance(df, start, end)
    if filtered.empty:
        return pd.DataFrame()

    rows = filtered.copy()
    rows["month_label"] = rows["report_month"].apply(
        lambda d: d.strftime("%b %Y") if isinstance(d, date) else str(d)
    )
    rows["net_revenue_per_class"] = (
        rows["studio_net"] / rows["class_count"].replace(0, pd.NA)
    ).fillna(0)

    month_order = (
        rows[["report_month", "month_label"]]
        .drop_duplicates()
        .sort_values("report_month")["month_label"]
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
            row = month_rows.iloc[0]
            record[f"classes_{month_label}"] = int(row["class_count"])
            record[f"attendance_{month_label}"] = float(row["average_attendance"])
            record[f"net_per_class_{month_label}"] = float(row["net_revenue_per_class"])
            record[f"studio_net_{month_label}"] = float(row["studio_net"])
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
        "description": "Momence instructor monthly reports overlapping the selected date range.",
        "file_prefix": "soma_instructor_performance",
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
) -> tuple[date, date]:
    bounds: list[date] = []
    if sales is not None and not sales.empty and "payment_date" in sales.columns:
        bounds.extend([sales["payment_date"].min(), sales["payment_date"].max()])
    if expenses is not None and not expenses.empty:
        bounds.extend([expenses["expense_date"].min(), expenses["expense_date"].max()])
    if instructors is not None and not instructors.empty:
        bounds.extend([instructors["report_month"].min(), instructors["report_month"].max()])
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
        return filtered[
            [
                "report_month",
                "instructor_name",
                "instructor_email",
                "average_attendance",
                "total_bookings",
                "gross_revenue",
                "instructor_payout",
                "studio_net",
                "class_count",
                "total_hours",
            ]
        ].sort_values(["report_month", "instructor_name"])

    return pd.DataFrame()
