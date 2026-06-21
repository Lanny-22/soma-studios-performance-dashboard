"""Budget vs actuals by financial-model period (13th–13th)."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import (
    BUDGET_REVENUE_CATEGORIES,
    add_cumulative_columns,
    build_budget_vs_actuals,
)
from dashboard.shared import BAR_CHART_HEIGHT, CHART_HEIGHT, EUR, GREEN, GREEN_LIGHT, PLOTLY_CONFIG


def _grouped_bar(
    df: pd.DataFrame,
    title: str,
    budget_col: str,
    actual_col: str,
    y_title: str,
    *,
    as_percent: bool = False,
) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Budget",
            x=df["period_label"],
            y=df[budget_col],
            marker_color=GREEN_LIGHT,
        )
    )
    fig.add_trace(
        go.Bar(
            name="Actual",
            x=df["period_label"],
            y=df[actual_col],
            marker_color=GREEN,
        )
    )
    fig.update_layout(
        title=title,
        barmode="group",
        xaxis_title="Period",
        yaxis_title=y_title,
        height=BAR_CHART_HEIGHT,
        margin=dict(l=48, r=24, t=56, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    if as_percent:
        fig.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _cumulative_line(
    df: pd.DataFrame,
    title: str,
    budget_col: str,
    actual_col: str,
    y_title: str,
    *,
    as_percent: bool = False,
) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            name="Budget (cumulative)",
            x=df["period_label"],
            y=df[budget_col],
            mode="lines+markers",
            line=dict(color=GREEN_LIGHT, width=3),
            marker=dict(size=8),
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Actual (cumulative)",
            x=df["period_label"],
            y=df[actual_col],
            mode="lines+markers",
            line=dict(color=GREEN, width=3),
            marker=dict(size=8),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Period end",
        yaxis_title=y_title,
        height=CHART_HEIGHT,
        margin=dict(l=48, r=24, t=56, b=48),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    if as_percent:
        fig.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _format_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return EUR.format(value)


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1f}%"


def _render_period_metrics(focus: pd.Series, label_prefix: str) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        f"{label_prefix} revenue",
        _format_money(focus["actual_revenue"]),
        delta=focus["revenue_variance"],
        delta_color="normal",
        help=f"Budget {_format_money(focus['budget_revenue'])}",
    )
    c2.metric(
        f"{label_prefix} instructor fees",
        _format_money(focus["actual_instructor_fees"]),
        delta=focus["instructor_variance"],
        delta_color="inverse",
        help=f"Budget {_format_money(focus['budget_instructor_fees'])}",
    )
    c3.metric(
        f"{label_prefix} gross profit",
        _format_money(focus["actual_gross_profit"]),
        delta=focus["actual_gross_profit"] - focus["budget_gross_profit"],
        help=f"Budget {_format_money(focus['budget_gross_profit'])}",
    )
    c4.metric(
        f"{label_prefix} gross margin",
        _format_pct(focus["actual_gross_margin_pct"]),
        delta=focus["margin_variance_pct"],
        delta_color="normal",
        help=f"Budget {_format_pct(focus['budget_gross_margin_pct'])}",
    )


def _render_cumulative_metrics(focus: pd.Series) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Cumulative revenue",
        _format_money(focus["cum_actual_revenue"]),
        delta=focus["cum_revenue_variance"],
        delta_color="normal",
        help=f"Budget to date {_format_money(focus['cum_budget_revenue'])}",
    )
    c2.metric(
        "Cumulative instructor fees",
        _format_money(focus["cum_actual_instructor_fees"]),
        delta=focus["cum_instructor_variance"],
        delta_color="inverse",
        help=f"Budget to date {_format_money(focus['cum_budget_instructor_fees'])}",
    )
    c3.metric(
        "Cumulative gross profit",
        _format_money(focus["cum_actual_gross_profit"]),
        delta=focus["cum_gross_profit_variance"],
        help=f"Budget to date {_format_money(focus['cum_budget_gross_profit'])}",
    )
    c4.metric(
        "Cumulative gross margin",
        _format_pct(focus["cum_actual_gross_margin_pct"]),
        delta=focus["cum_margin_variance_pct"],
        delta_color="normal",
        help=f"Budget to date {_format_pct(focus['cum_budget_gross_margin_pct'])}",
    )


def render(
    sales: pd.DataFrame,
    instructors: pd.DataFrame | None,
    budget: pd.DataFrame,
) -> None:
    st.title("Budget vs Actuals")
    st.caption(
        "Compares the financial model to Momence actuals by **studio period** "
        "(13th → 12th, anchored on launch 13 May 2026). "
        f"Revenue actuals = net sales for {', '.join(BUDGET_REVENUE_CATEGORIES)} "
        "by **payment date** (Malta). Instructor actuals = Momence class payouts by **class date**. "
        "Use **Cumulative** to see running totals — monthly swings can offset when viewed together."
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
    focus = started[current_mask].iloc[-1] if current_mask.any() else started.iloc[-1]
    cum_focus = cumulative.iloc[-1]
    focus_label = focus["period_label"]
    is_current = bool(current_mask.any() and focus["period_end"] >= today)

    if is_current:
        st.info(
            f"**{focus_label}** is in progress ({focus['period_range']}). "
            "Actuals below are partial for this period."
        )

    st.markdown(f"**Current period — {focus_label}**")
    _render_period_metrics(focus, focus_label)

    st.markdown(
        f"**Cumulative through {focus_label}** "
        f"({started.iloc[0]['period_start']:%d %b %Y} – {focus['period_end']:%d %b %Y})"
    )
    _render_cumulative_metrics(cum_focus)

    monthly_tab, cumulative_tab = st.tabs(["Monthly by period", "Cumulative"])

    with monthly_tab:
        st.subheader("Revenue")
        _grouped_bar(
            started,
            "Budget vs actual revenue per period",
            "budget_revenue",
            "actual_revenue",
            "EUR",
        )

        st.subheader("Instructor fees")
        _grouped_bar(
            started,
            "Budget vs actual instructor / coach fees per period",
            "budget_instructor_fees",
            "actual_instructor_fees",
            "EUR",
        )

        st.subheader("Gross margin")
        margin_df = started.copy()
        margin_df["actual_gross_margin_pct"] = margin_df["actual_gross_margin_pct"].fillna(0)
        _grouped_bar(
            margin_df,
            "Budget vs actual gross margin % per period",
            "budget_gross_margin_pct",
            "actual_gross_margin_pct",
            "Margin %",
            as_percent=True,
        )

        st.subheader("Period detail")
        display = started.copy()
        display["Budget revenue"] = display["budget_revenue"].map(lambda v: EUR.format(v))
        display["Actual revenue"] = display["actual_revenue"].map(lambda v: EUR.format(v))
        display["Revenue Δ"] = display["revenue_variance"].map(lambda v: EUR.format(v))
        display["Budget instructor"] = display["budget_instructor_fees"].map(lambda v: EUR.format(v))
        display["Actual instructor"] = display["actual_instructor_fees"].map(lambda v: EUR.format(v))
        display["Budget margin"] = display["budget_gross_margin_pct"].map(_format_pct)
        display["Actual margin"] = display["actual_gross_margin_pct"].map(_format_pct)

        st.dataframe(
            display[
                [
                    "period_label",
                    "period_range",
                    "Budget revenue",
                    "Actual revenue",
                    "Revenue Δ",
                    "Budget instructor",
                    "Actual instructor",
                    "Budget margin",
                    "Actual margin",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    with cumulative_tab:
        st.caption(
            "Running totals from launch through each period end. "
            "Cumulative gross margin = cumulative gross profit ÷ cumulative revenue."
        )

        st.subheader("Cumulative revenue")
        _cumulative_line(
            cumulative,
            "Running total revenue — budget vs actual",
            "cum_budget_revenue",
            "cum_actual_revenue",
            "EUR",
        )
        _grouped_bar(
            cumulative,
            "Cumulative revenue at each period end",
            "cum_budget_revenue",
            "cum_actual_revenue",
            "EUR",
        )

        st.subheader("Cumulative instructor fees")
        _cumulative_line(
            cumulative,
            "Running total instructor fees — budget vs actual",
            "cum_budget_instructor_fees",
            "cum_actual_instructor_fees",
            "EUR",
        )

        st.subheader("Cumulative gross margin")
        cum_margin = cumulative.copy()
        cum_margin["cum_actual_gross_margin_pct"] = cum_margin[
            "cum_actual_gross_margin_pct"
        ].fillna(0)
        _cumulative_line(
            cum_margin,
            "Cumulative gross margin % — budget vs actual",
            "cum_budget_gross_margin_pct",
            "cum_actual_gross_margin_pct",
            "Margin %",
            as_percent=True,
        )
        st.caption(
            "Budget cumulative margin uses model gross profit (includes inventory COGS). "
            "Actual cumulative margin is (cumulative revenue − cumulative instructor payouts) ÷ cumulative revenue."
        )

        st.subheader("Cumulative detail")
        cum_display = cumulative.copy()
        cum_display["Budget revenue"] = cum_display["cum_budget_revenue"].map(
            lambda v: EUR.format(v)
        )
        cum_display["Actual revenue"] = cum_display["cum_actual_revenue"].map(
            lambda v: EUR.format(v)
        )
        cum_display["Revenue Δ"] = cum_display["cum_revenue_variance"].map(
            lambda v: EUR.format(v)
        )
        cum_display["Budget instructor"] = cum_display["cum_budget_instructor_fees"].map(
            lambda v: EUR.format(v)
        )
        cum_display["Actual instructor"] = cum_display["cum_actual_instructor_fees"].map(
            lambda v: EUR.format(v)
        )
        cum_display["Budget margin"] = cum_display["cum_budget_gross_margin_pct"].map(
            _format_pct
        )
        cum_display["Actual margin"] = cum_display["cum_actual_gross_margin_pct"].map(
            _format_pct
        )

        st.dataframe(
            cum_display[
                [
                    "period_label",
                    "period_range",
                    "Budget revenue",
                    "Actual revenue",
                    "Revenue Δ",
                    "Budget instructor",
                    "Actual instructor",
                    "Budget margin",
                    "Actual margin",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
