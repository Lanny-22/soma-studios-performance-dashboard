"""LEGACY: Peak Times from Total Sales service_at — kept for reference, not used in nav."""

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
)

METRIC_TOTAL = "Total net sales"
METRIC_PER_CLASS = "Net sales per class"
METRIC_UTILIZATION = "Utilization per class"
METRIC_OPTIONS = [METRIC_TOTAL, METRIC_PER_CLASS, METRIC_UTILIZATION]

METRIC_CONFIG: dict[str, tuple[str, str, str]] = {
    METRIC_TOTAL: ("net_sales", "Net sales (EUR)", "currency"),
    METRIC_PER_CLASS: ("revenue_per_class", "Net sales per class (€)", "currency"),
    METRIC_UTILIZATION: (
        "utilization_per_class",
        "Bookings per class (utilization)",
        "rate",
    ),
}


def _format_value(metric: str, value: float) -> str:
    kind = METRIC_CONFIG[metric][2]
    if kind == "currency":
        return EUR.format(value)
    if kind == "rate":
        return f"{value:.1f}"
    return f"{int(value)}"


def _heatmap(matrix: pd.DataFrame, value_col: str, title: str, kind: str) -> None:
    if matrix.empty:
        st.info("No class sessions in this range.")
        return

    hours = sorted(int(h) for h in matrix["service_hour"].unique())
    hour_labels = [f"{h:02d}:00" for h in hours]
    z_rows: list[list[float]] = []
    y_labels: list[str] = []

    for day in DAY_ORDER:
        row_vals: list[float] = []
        for hour in hours:
            match = matrix[
                (matrix["service_day"] == day) & (matrix["service_hour"] == hour)
            ]
            val = float(match[value_col].sum()) if not match.empty else 0.0
            row_vals.append(val)
        if any(v > 0 for v in row_vals):
            y_labels.append(day)
            z_rows.append(row_vals)

    if not z_rows:
        st.info("No class sessions in this range.")
        return

    z_max = max(max(row) for row in z_rows)
    if kind == "currency":
        hover = "%{y} %{x}<br>€%{z:,.2f}<extra></extra>"
        colorbar_title = "€"
    elif kind == "rate":
        hover = "%{y} %{x}<br>%{z:.1f} bookings/class<extra></extra>"
        colorbar_title = "Bookings/class"
    else:
        hover = "%{y} %{x}<br>Count: %{z:,.0f}<extra></extra>"
        colorbar_title = "Count"

    fig = go.Figure(
        data=go.Heatmap(
            z=z_rows,
            x=hour_labels,
            y=y_labels,
            colorscale=[[0, "#f8f9fa"], [0.35, GREEN_LIGHT], [1, GREEN]],
            zmin=0,
            zmax=z_max if z_max > 0 else 1,
            hovertemplate=hover,
            showscale=True,
            colorbar=dict(title=colorbar_title),
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


def _bar_chart(
    df: pd.DataFrame,
    x_col: str,
    metric: str,
    title: str,
    color: str,
    x_title: str,
) -> None:
    if df.empty:
        return

    value_col, y_label, kind = METRIC_CONFIG[metric]
    labels = df[x_col]
    if x_col == "service_hour":
        labels = df[x_col].map(lambda h: f"{int(h):02d}:00")

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=df[value_col],
            marker_color=color,
            text=df[value_col].map(lambda v: _format_value(metric, v)),
            textposition="outside",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title=y_label,
        height=CHART_HEIGHT // 2,
        margin=dict(l=48, r=24, t=56, b=48),
    )
    if kind == "currency":
        fig.update_yaxes(tickformat=",.0f")
    elif kind == "rate":
        fig.update_yaxes(tickformat=".1f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Peak Times (legacy — sales service times)")
    st.caption(
        "When classes run (Momence **service date/time**, Malta). "
        "Compare **net sales per class** and **utilization per class** (avg bookings per session) "
        "to judge slots fairly — busy hours often run more classes, not better ones."
    )

    category = st.sidebar.radio(
        "Sales type",
        options=["Class", "All categories"],
        horizontal=True,
        key="peak_times_legacy_category",
    )
    metric = st.sidebar.radio(
        "Compare by",
        options=METRIC_OPTIONS,
        horizontal=False,
        key="peak_times_legacy_metric",
    )

    classes = raw[raw["category"] == "Class"].copy() if category == "Class" else raw.copy()
    filtered = filter_service_date_range(classes, start, end)

    if filtered.empty:
        st.warning("No sales with service times in the selected date range.")
        return

    total = filtered["net_sales"].sum()
    class_sessions = int(filtered["service_at"].nunique())
    transactions = len(filtered)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Net sales", EUR.format(total))
    c2.metric("Class sessions", f"{class_sessions:,}")
    c3.metric("Bookings", f"{transactions:,}")
    c4.metric(
        "Net sales / class",
        EUR.format(total / class_sessions) if class_sessions else "—",
    )
    c5.metric(
        "Utilization / class",
        f"{transactions / class_sessions:.1f}" if class_sessions else "—",
        help="Average bookings per class session in this range.",
    )

    tab_day, tab_hour, tab_matrix = st.tabs(
        ["By day of week", "By hour", "Day × hour heatmap"]
    )

    matrix = schedule_timing_matrix(filtered)
    days = day_of_week_totals(filtered)
    hours = hour_totals(filtered)
    value_col, _, kind = METRIC_CONFIG[metric]

    with tab_day:
        _bar_chart(days, "service_day", metric, f"{metric} by day of week", GREEN, "Day")
    with tab_hour:
        _bar_chart(
            hours, "service_hour", metric, f"{metric} by hour of day", BLACK, "Hour (Malta)"
        )
    with tab_matrix:
        _heatmap(matrix, value_col, f"{metric} by day and hour", kind)
