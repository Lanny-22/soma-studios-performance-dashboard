"""Load Momence sales data from Supabase for the analytics dashboard."""

import calendar
from datetime import date

import pandas as pd

from src.db import get_conn

SALES_QUERY = """
    SELECT
        payment_at,
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
    df["sale_date"] = df["payment_at"].dt.date
    df["sale_value"] = pd.to_numeric(df["sale_value"], errors="coerce").fillna(0)
    df["refunded"] = pd.to_numeric(df["refunded"], errors="coerce").fillna(0)
    df["net_sales"] = df["sale_value"] - df["refunded"]
    df["category"] = df["category"].fillna("Unknown")
    return df


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
