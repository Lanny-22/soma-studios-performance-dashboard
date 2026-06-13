"""Load Momence sales data from Supabase for the analytics dashboard."""

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
