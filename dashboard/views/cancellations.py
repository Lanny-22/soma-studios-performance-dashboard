"""Membership cancellations over time and reason categories."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.data import (
    cancellation_reason_breakdown,
    daily_cancellation_totals,
    filter_cancellations,
)
from dashboard.shared import BAR_CHART_HEIGHT, CHART_HEIGHT, DAY_MS, GREEN, PLOTLY_CONFIG

REF_LINE = "rgba(27, 27, 27, 0.2)"

CATEGORY_COLORS = {
    "Travel / away": "#2d6a4f",
    "Cost / affordability": "#40916c",
    "Too busy / schedule": "#74c69d",
    "Switching membership": "#95d5b2",
    "Other / unspecified": "#1b1b1b",
}


def _metric_row(daily: pd.DataFrame, total: int, start: date, end: date) -> None:
    calendar_days = max((end - start).days + 1, 1)
    avg_daily = total / calendar_days
    peak_idx = daily["cancellations"].idxmax()
    peak_date = daily.loc[peak_idx, "cancel_date"]
    peak_val = int(daily.loc[peak_idx, "cancellations"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cancellations (filtered)", f"{total:,}")
    c2.metric("Peak day", f"{peak_val:,}", help=f"Most cancellations on {peak_date}")
    c3.metric(
        "Average per day",
        f"{avg_daily:.2f}",
        help=f"Cancellations ÷ {calendar_days} days in selected range",
    )
    c4.metric(
        "Days with cancellations",
        f"{len(daily):,}",
        help=f"Out of {calendar_days} days in range",
    )


def _daily_chart(daily: pd.DataFrame, avg_daily: float, max_daily: float) -> None:
    labels = daily["cancellations"].map(lambda v: f"{int(v)}")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=daily["cancel_date"],
            y=daily["cancellations"],
            name="Daily cancellations",
            marker_color=GREEN,
            width=DAY_MS * 0.92,
            text=labels,
            textposition="outside",
            textangle=-90,
            cliponaxis=False,
        )
    )
    fig.add_hline(y=max_daily, line_dash="dot", line_color=REF_LINE, line_width=2.5)
    fig.add_hline(y=avg_daily, line_dash="dot", line_color=REF_LINE, line_width=2.5)
    fig.update_layout(
        title="Daily cancellations",
        xaxis_title="Date",
        yaxis_title="Cancellations",
        height=CHART_HEIGHT,
        margin=dict(l=48, r=24, t=80, b=48),
        hovermode="x unified",
        autosize=True,
        bargap=0.06,
        uniformtext_minsize=8,
        uniformtext_mode="hide",
    )
    fig.update_yaxes(tickformat=",.0f", dtick=1 if max_daily <= 10 else None)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _category_chart(breakdown: pd.DataFrame) -> None:
    colors = [
        CATEGORY_COLORS.get(str(cat), GREEN) for cat in breakdown["reason_category"]
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=breakdown["reason_category"].astype(str),
            y=breakdown["cancellations"],
            marker_color=colors,
            text=breakdown["cancellations"].map(lambda v: f"{int(v)}"),
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        title="Cancellation reasons",
        xaxis_title="Category",
        yaxis_title="Cancellations",
        height=BAR_CHART_HEIGHT,
        margin=dict(l=48, r=24, t=80, b=80),
        autosize=True,
        showlegend=False,
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _reason_samples(filtered: pd.DataFrame) -> None:
    with st.expander("Sample raw reasons by category"):
        for category in filtered["reason_category"].dropna().unique():
            sample = (
                filtered.loc[filtered["reason_category"] == category, "reason"]
                .fillna("")
                .replace("", "(blank)")
                .value_counts()
                .head(5)
            )
            st.markdown(f"**{category}**")
            for reason, count in sample.items():
                st.caption(f"{count}× — {reason}")


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Cancellations")
    st.caption(
        "Momence membership cancellations by payment/cancel date. "
        "Reasons are grouped from the Momence **Reason** field (including free-text notes)."
    )

    filtered = filter_cancellations(raw, start, end)
    if filtered.empty:
        st.warning("No cancellations in the selected date range.")
        return

    daily = daily_cancellation_totals(filtered)
    total = int(len(filtered))
    calendar_days = max((end - start).days + 1, 1)
    avg_daily = total / calendar_days
    max_daily = float(daily["cancellations"].max())

    _metric_row(daily, total, start, end)
    _daily_chart(daily, avg_daily, max_daily)

    breakdown = cancellation_reason_breakdown(filtered)
    st.subheader("Why people cancel")
    st.caption(
        "Categories are rule-based from Reason text: Travel / away, Cost, Too busy, "
        "Switching membership, and Other."
    )
    _category_chart(breakdown)
    _reason_samples(filtered)
