"""Budget vs actuals by financial-model period (13th–13th)."""

from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd
import streamlit as st

from dashboard.data import (
    BUDGET_REVENUE_CATEGORIES,
    add_cumulative_columns,
    build_budget_vs_actuals,
)
from dashboard.shared import EUR

MetricFmt = Callable[[float | None], str]


def _format_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    amount = float(value)
    if abs(amount) >= 1000:
        thousands = amount / 1000
        if abs(thousands - round(thousands)) < 0.05:
            return f"€{int(round(thousands)):,}k".replace(",", "")
        return EUR.format(amount)
    return EUR.format(amount)


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.0f}%"


METRIC_ROWS: list[tuple[str, str, str, MetricFmt]] = [
    ("Revenue", "actual_revenue", "budget_revenue", _format_money),
    ("Instructor Fees", "actual_instructor_fees", "budget_instructor_fees", _format_money),
    ("Gross Margin", "actual_gross_margin_pct", "budget_gross_margin_pct", _format_pct),
]

CUM_METRIC_ROWS: list[tuple[str, str, str, MetricFmt]] = [
    ("Revenue", "cum_actual_revenue", "cum_budget_revenue", _format_money),
    (
        "Instructor Fees",
        "cum_actual_instructor_fees",
        "cum_budget_instructor_fees",
        _format_money,
    ),
    (
        "Gross Margin",
        "cum_actual_gross_margin_pct",
        "cum_budget_gross_margin_pct",
        _format_pct,
    ),
]


def _pivot_table(df: pd.DataFrame, metrics: list[tuple[str, str, str, MetricFmt]]) -> pd.DataFrame:
    """Metrics down the side, periods across the top — Actual/Budget row pairs."""
    period_codes = df["period_code"].tolist()
    by_period = df.set_index("period_code")

    rows: list[dict[str, str]] = []
    for label, actual_col, budget_col, fmt in metrics:
        actual_row: dict[str, str] = {"Metric": label, "": "Actual"}
        budget_row: dict[str, str] = {"Metric": "", "": "Budget"}
        for code in period_codes:
            period = by_period.loc[code]
            actual_row[code] = fmt(period[actual_col])
            budget_row[code] = fmt(period[budget_col])
        rows.extend([actual_row, budget_row])

    table = pd.DataFrame(rows)
    table = table[["Metric", ""] + period_codes]
    table.columns = ["Metric", ""] + [
        f"{code}\n{by_period.loc[code]['period_range']}" for code in period_codes
    ]
    return table


def _style_pivot(table: pd.DataFrame):
    def _metric_style(col: pd.Series) -> list[str]:
        return [
            "background-color: #f3f4f6; font-weight: 600" if value else ""
            for value in col
        ]

    return table.style.apply(_metric_style, subset=["Metric"])


def render(
    sales: pd.DataFrame,
    instructors: pd.DataFrame | None,
    budget: pd.DataFrame,
) -> None:
    st.title("Budget vs Actuals")
    st.caption(
        "Financial model vs Momence actuals by **studio period** (13th → 12th, from 13 May 2026). "
        f"Revenue = {', '.join(BUDGET_REVENUE_CATEGORIES)} net sales by payment date. "
        "Instructor fees = Momence class payouts by class date."
    )

    if budget.empty:
        st.warning("No financial model periods found. Run `python3 scripts/run_financial_model_import.py`.")
        return

    instructor_df = instructors if instructors is not None else pd.DataFrame()
    comparison = build_budget_vs_actuals(sales, instructor_df, budget)
    if comparison.empty:
        st.warning("Could not build budget comparison.")
        return

    today = date.today()
    started = comparison[comparison["period_start"] <= today].copy()
    if started.empty:
        st.info("No studio periods have started yet.")
        return

    cumulative = add_cumulative_columns(started)

    current_mask = (started["period_start"] <= today) & (started["period_end"] >= today)
    if current_mask.any() and started.loc[current_mask, "period_end"].iloc[-1] >= today:
        focus = started[current_mask].iloc[-1]
        st.info(
            f"**{focus['period_label']}** is in progress ({focus['period_range']}). "
            "Actual figures for that period are partial."
        )

    monthly_tab, cumulative_tab = st.tabs(["Monthly by period", "Cumulative"])

    with monthly_tab:
        st.dataframe(
            _style_pivot(_pivot_table(started, METRIC_ROWS)),
            use_container_width=True,
            hide_index=True,
        )

    with cumulative_tab:
        st.caption(
            "Running totals through each period end. "
            "Gross margin = cumulative gross profit ÷ cumulative revenue."
        )
        st.dataframe(
            _style_pivot(_pivot_table(cumulative, CUM_METRIC_ROWS)),
            use_container_width=True,
            hide_index=True,
        )
