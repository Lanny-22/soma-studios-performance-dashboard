"""Total sales overview — daily and cumulative charts."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import daily_totals, filter_sales
from dashboard.shared import (
    BAR_CHART_HEIGHT,
    BLACK,
    CHART_HEIGHT,
    DAY_MS,
    EUR,
    GREEN,
    GREEN_LIGHT,
    PLOTLY_CONFIG,
)


def _metric_row(
    daily: pd.DataFrame,
    total: float,
    transactions: int,
    start: date,
    end: date,
) -> None:
    calendar_days = max((end - start).days + 1, 1)
    avg_daily = total / calendar_days

    best_idx = daily["net_sales"].idxmax()
    best_date = daily.loc[best_idx, "sale_date"]
    best_val = float(daily.loc[best_idx, "net_sales"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net sales (filtered)", EUR.format(total), help=f"{transactions:,} transactions")
    c2.metric("Best single day", EUR.format(best_val), help=f"Peak net sales on {best_date}")
    c3.metric(
        "Average daily sales",
        EUR.format(avg_daily),
        help=f"Net sales ÷ {calendar_days} days in selected range",
    )
    c4.metric("Days with sales", f"{len(daily):,}", help=f"Out of {calendar_days} days in range")


REF_LINE = "rgba(27, 27, 27, 0.2)"


def _daily_chart(daily: pd.DataFrame, avg_daily: float, max_daily: float) -> None:
    labels = daily["net_sales"].map(lambda v: f"€{v:,.0f}")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=daily["sale_date"],
            y=daily["net_sales"],
            name="Daily net sales",
            marker_color=GREEN,
            width=DAY_MS * 0.92,
            text=labels,
            textposition="outside",
            textangle=-90,
            cliponaxis=False,
        )
    )
    fig.add_hline(
        y=max_daily,
        line_dash="dot",
        line_color=REF_LINE,
        line_width=2.5,
    )
    fig.add_hline(
        y=avg_daily,
        line_dash="dot",
        line_color=REF_LINE,
        line_width=2.5,
    )
    fig.update_layout(
        title="Daily net sales",
        xaxis_title="Date",
        yaxis_title="Net sales (EUR)",
        height=CHART_HEIGHT,
        margin=dict(l=48, r=24, t=80, b=48),
        hovermode="x unified",
        autosize=True,
        bargap=0.06,
        uniformtext_minsize=8,
        uniformtext_mode="hide",
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _cumulative_chart(daily: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily["sale_date"],
            y=daily["cumulative_sales"],
            mode="lines+markers",
            name="Cumulative net sales",
            line=dict(color=GREEN_LIGHT, width=3),
            marker=dict(size=8),
        )
    )

    last = daily.iloc[-1]
    final_date = last["sale_date"]
    final_val = float(last["cumulative_sales"])
    label = EUR.format(final_val)

    fig.add_trace(
        go.Scatter(
            x=[final_date],
            y=[final_val],
            mode="markers",
            name="Final total",
            marker=dict(size=14, color=BLACK, line=dict(width=2, color="#ffffff")),
            showlegend=False,
            hovertemplate=f"{final_date}<br>Cumulative: {label}<extra></extra>",
        )
    )
    fig.add_annotation(
        x=final_date,
        y=final_val,
        text=label,
        showarrow=True,
        arrowhead=2,
        arrowsize=1.2,
        arrowwidth=1.5,
        arrowcolor=BLACK,
        ax=50,
        ay=-48,
        bgcolor="rgba(255, 255, 255, 0.95)",
        bordercolor=BLACK,
        borderwidth=1,
        borderpad=6,
        font=dict(size=14, color=BLACK),
    )

    fig.update_layout(
        title="Cumulative net sales",
        xaxis_title="Date",
        yaxis_title="Cumulative net sales (EUR)",
        height=CHART_HEIGHT,
        margin=dict(l=48, r=24, t=56, b=48),
        hovermode="x unified",
        autosize=True,
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Total Sales")
    st.caption("Momence Total Sales · filtered view")

    all_categories = sorted(raw["category"].unique())
    selected_categories = st.sidebar.multiselect(
        "Product type (category)",
        options=all_categories,
        default=all_categories,
        help="Momence category: Pack, Class, Product, Subscription, etc.",
    )

    filtered = filter_sales(raw, selected_categories, start, end)
    daily = daily_totals(filtered)

    if filtered.empty:
        st.warning("No rows match the current filters.")
        return

    total = filtered["net_sales"].sum()
    transactions = len(filtered)
    calendar_days = max((end - start).days + 1, 1)
    avg_daily = total / calendar_days
    max_daily = float(daily["net_sales"].max())

    _metric_row(daily, total, transactions, start, end)

    _daily_chart(daily, avg_daily, max_daily)
    _cumulative_chart(daily)

    with st.expander("Category breakdown"):
        breakdown = (
            filtered.groupby("category", as_index=False)
            .agg(net_sales=("net_sales", "sum"), count=("sale_reference", "count"))
            .sort_values("net_sales", ascending=False)
        )
        breakdown["net_sales"] = breakdown["net_sales"].map(lambda v: EUR.format(v))
        st.dataframe(breakdown, use_container_width=True, hide_index=True)
