"""Budget vs actuals by financial-model period (13th–13th)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from dashboard.data import (
    BUDGET_REVENUE_CATEGORIES,
    add_cumulative_columns,
    build_budget_vs_actuals,
)
from dashboard.shared import EUR


def _format_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return EUR.format(value)


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1f}%"


def _variance_money(actual: float, budget: float) -> str:
    return _format_money(actual - budget)


def _variance_pct(actual: float | None, budget: float) -> str:
    if actual is None or pd.isna(actual):
        return "—"
    return f"{actual - budget:+.1f}pp"


def _monthly_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "Period": r["period_label"],
                "Dates": r["period_range"],
                "Budget revenue": _format_money(r["budget_revenue"]),
                "Actual revenue": _format_money(r["actual_revenue"]),
                "Revenue Δ": _variance_money(r["actual_revenue"], r["budget_revenue"]),
                "Budget instructor": _format_money(r["budget_instructor_fees"]),
                "Actual instructor": _format_money(r["actual_instructor_fees"]),
                "Instructor Δ": _variance_money(
                    r["actual_instructor_fees"], r["budget_instructor_fees"]
                ),
                "Budget gross profit": _format_money(r["budget_gross_profit"]),
                "Actual gross profit": _format_money(r["actual_gross_profit"]),
                "Gross profit Δ": _variance_money(
                    r["actual_gross_profit"], r["budget_gross_profit"]
                ),
                "Budget margin": _format_pct(r["budget_gross_margin_pct"]),
                "Actual margin": _format_pct(r["actual_gross_margin_pct"]),
                "Margin Δ": _variance_pct(
                    r["actual_gross_margin_pct"], r["budget_gross_margin_pct"]
                ),
            }
        )
    return pd.DataFrame(rows)


def _cumulative_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "Through period": r["period_label"],
                "Dates": r["period_range"],
                "Budget revenue": _format_money(r["cum_budget_revenue"]),
                "Actual revenue": _format_money(r["cum_actual_revenue"]),
                "Revenue Δ": _variance_money(r["cum_actual_revenue"], r["cum_budget_revenue"]),
                "Budget instructor": _format_money(r["cum_budget_instructor_fees"]),
                "Actual instructor": _format_money(r["cum_actual_instructor_fees"]),
                "Instructor Δ": _variance_money(
                    r["cum_actual_instructor_fees"], r["cum_budget_instructor_fees"]
                ),
                "Budget gross profit": _format_money(r["cum_budget_gross_profit"]),
                "Actual gross profit": _format_money(r["cum_actual_gross_profit"]),
                "Gross profit Δ": _variance_money(
                    r["cum_actual_gross_profit"], r["cum_budget_gross_profit"]
                ),
                "Budget margin": _format_pct(r["cum_budget_gross_margin_pct"]),
                "Actual margin": _format_pct(r["cum_actual_gross_margin_pct"]),
                "Margin Δ": _variance_pct(
                    r["cum_actual_gross_margin_pct"],
                    r["cum_budget_gross_margin_pct"],
                ),
            }
        )
    return pd.DataFrame(rows)


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
            "Actual figures for that row are partial."
        )

    monthly_tab, cumulative_tab = st.tabs(["Monthly by period", "Cumulative"])

    with monthly_tab:
        st.dataframe(
            _monthly_table(started),
            use_container_width=True,
            hide_index=True,
        )

    with cumulative_tab:
        st.caption(
            "Running totals from launch through each period end. "
            "Margin = cumulative gross profit ÷ cumulative revenue."
        )
        st.dataframe(
            _cumulative_table(cumulative),
            use_container_width=True,
            hide_index=True,
        )
