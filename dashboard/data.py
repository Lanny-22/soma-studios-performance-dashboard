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
    month_key: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    filtered = df.copy()

    if categories:
        filtered = filtered[filtered["category"].isin(categories)]

    if month_key == "april":
        filtered = filtered[
            (filtered["sale_date"] >= date(2026, 4, 1))
            & (filtered["sale_date"] <= date(2026, 4, 30))
        ]
    elif month_key == "may":
        filtered = filtered[
            (filtered["sale_date"] >= date(2026, 5, 1))
            & (filtered["sale_date"] <= date(2026, 5, 31))
        ]

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
