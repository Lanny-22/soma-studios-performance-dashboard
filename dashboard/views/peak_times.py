"""Sales performance by day of week and hour of day (class service times)."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import (
    DAY_ORDER,
    day_of_week_totals,
    filter_service_date_range,
    hour_totals,
    schedule_timing_matrix,
)
from dashboard.shared import (
    BLACK,
    CHART_HEIGHT,
    EUR,
    GREEN,
    GREEN_LIGHT,
    PLOTLY_CONFIG,
    operating_view_banner,
)


def _heatmap(matrix: pd.DataFrame, value_col: str, title: str, z_title: str) -> None:
    if matrix.empty:
        st.info("No class bookings with service times in this range.")
        return

    hours = sorted(matrix["service_hour"].unique())
    hour_labels = [f"{h:02d}:00" for h in hours]
    z_rows: list[list[float]] = []
    y_labels: list[str] = []
    text_rows: list[list[str]] = []

    for day in DAY_ORDER:
        row_vals: list[float] = []
        row_text: list[str] = []
        for hour in hours:
            match = matrix[
                (matrix["service_day"] == day) & (matrix["service_hour"] == hour)
            ]
            val = float(match[value_col].sum()) if not match.empty else 0.0
            row_vals.append(val)
            row_text.append(f"€{val:,.0f}" if value_col == "net_sales" else f"{int(val)}")
        if any(v > 0 for v in row_vals):
            y_labels.append(day)
            z_rows.append(row_vals)
            text_rows.append(row_text)

    if not z_rows:
        st.info("No class bookings with service times in this range.")
        return

    fig = go.Figure(
        data=go.Heatmap(
            z=z_rows,
            x=hour_labels,
            y=y_labels,
            colorscale=[[0, "#f8f9fa"], [0.35, GREEN_LIGHT], [1, GREEN]],
            text=text_rows,
            texttemplate="%{text}",
            hovertemplate="%{y} %{x}<br>" + z_title + ": %{text}<extra></extra>",
            showscale=True,
            colorbar=dict(title=z_title),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Hour (Malta)",
        yaxis_title="",
        height=max(360, 56 * len(y_labels) + 120),
        margin=dict(l=10, r=24, t=56, b=48),
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _day_chart(df: pd.DataFrame) -> None:
    if df.empty:
        return
    fig = go.Figure(
        go.Bar(
            x=df["service_day"],
            y=df["net_sales"],
            marker_color=GREEN,
            text=df["net_sales"].map(lambda v: f"€{v:,.0f}"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Net sales by day of week",
        xaxis_title="Day",
        yaxis_title="Net sales (EUR)",
        height=CHART_HEIGHT // 2,
        margin=dict(l=48, r=24, t=56, b=48),
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _hour_chart(df: pd.DataFrame) -> None:
    if df.empty:
        return
    labels = df["service_hour"].map(lambda h: f"{int(h):02d}:00")
    fig = go.Figure(
        go.Bar(
            x=labels,
            y=df["net_sales"],
            marker_color=BLACK,
            text=df["net_sales"].map(lambda v: f"€{v:,.0f}"),
            textposition="outside",
        )
    )
    fig.update_layout(
        title="Net sales by hour of day",
        xaxis_title="Hour (Malta)",
        yaxis_title="Net sales (EUR)",
        height=CHART_HEIGHT // 2,
        margin=dict(l=48, r=24, t=56, b=48),
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Peak Times")
    operating_view_banner()
    st.caption(
        "When classes actually run, based on Momence **service date/time** (Malta). "
        "Use this to spot strong days and hours for scheduling and instructor placement."
    )

    category = st.sidebar.radio(
        "Sales type",
        options=["Class", "All categories"],
        horizontal=True,
        key="peak_times_category",
    )

    classes = raw[raw["category"] == "Class"].copy() if category == "Class" else raw.copy()
    filtered = filter_service_date_range(classes, start, end)

    if filtered.empty:
        st.warning("No sales with service times in the selected date range.")
        return

    total = filtered["net_sales"].sum()
    transactions = len(filtered)
    c1, c2, c3 = st.columns(3)
    c1.metric("Net sales", EUR.format(total))
    c2.metric("Bookings", f"{transactions:,}")
    c3.metric(
        "Avg per booking",
        EUR.format(total / transactions) if transactions else "—",
    )

    tab_day, tab_hour, tab_matrix = st.tabs(
        ["By day of week", "By hour", "Day × hour heatmap"]
    )

    matrix = schedule_timing_matrix(filtered)
    days = day_of_week_totals(filtered)
    hours = hour_totals(filtered)

    with tab_day:
        _day_chart(days)
        if not days.empty:
            best = days.loc[days["net_sales"].idxmax()]
            st.caption(
                f"Strongest day: **{best['service_day']}** "
                f"({EUR.format(best['net_sales'])}, {int(best['transactions'])} bookings)"
            )

    with tab_hour:
        _hour_chart(hours)
        if not hours.empty:
            best = hours.loc[hours["net_sales"].idxmax()]
            st.caption(
                f"Peak hour: **{int(best['service_hour']):02d}:00** "
                f"({EUR.format(best['net_sales'])}, {int(best['transactions'])} bookings)"
            )

    with tab_matrix:
        _heatmap(matrix, "net_sales", "Net sales by day and hour", "Net sales")
        with st.expander("Booking count heatmap"):
            _heatmap(matrix, "transactions", "Bookings by day and hour", "Bookings")
