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
)

METRIC_TOTAL = "Total net sales"
METRIC_PER_CLASS = "Net sales per class"
METRIC_OPTIONS = [METRIC_TOTAL, METRIC_PER_CLASS]
VALUE_COL = {
    METRIC_TOTAL: "net_sales",
    METRIC_PER_CLASS: "revenue_per_class",
}


def _metric_label(metric: str) -> str:
    return "Net sales per class (€)" if metric == METRIC_PER_CLASS else "Net sales (EUR)"


def _format_value(metric: str, value: float) -> str:
    return EUR.format(value)


def _heatmap(matrix: pd.DataFrame, value_col: str, title: str, currency: bool = True) -> None:
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
    if currency:
        hover = "%{y} %{x}<br>€%{z:,.2f}<extra></extra>"
        colorbar_title = "€"
    else:
        hover = "%{y} %{x}<br>Count: %{z:,.0f}<extra></extra>"
        colorbar_title = "Sessions"

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

    value_col = VALUE_COL[metric]
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
        yaxis_title=_metric_label(metric),
        height=CHART_HEIGHT // 2,
        margin=dict(l=48, r=24, t=56, b=48),
    )
    if metric == METRIC_TOTAL:
        fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Peak Times")
    st.caption(
        "When classes run (Momence **service date/time**, Malta). "
        "Use **per class** to compare slots fairly — busy hours often have more sessions, "
        "not necessarily better revenue per class."
    )

    category = st.sidebar.radio(
        "Sales type",
        options=["Class", "All categories"],
        horizontal=True,
        key="peak_times_category",
    )
    metric = st.sidebar.radio(
        "Compare by",
        options=METRIC_OPTIONS,
        horizontal=True,
        key="peak_times_metric",
    )

    classes = raw[raw["category"] == "Class"].copy() if category == "Class" else raw.copy()
    filtered = filter_service_date_range(classes, start, end)

    if filtered.empty:
        st.warning("No sales with service times in the selected date range.")
        return

    total = filtered["net_sales"].sum()
    class_sessions = int(filtered["service_at"].nunique())
    transactions = len(filtered)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net sales", EUR.format(total))
    c2.metric("Class sessions", f"{class_sessions:,}")
    c3.metric("Bookings", f"{transactions:,}")
    c4.metric(
        "Avg per class",
        EUR.format(total / class_sessions) if class_sessions else "—",
    )

    tab_day, tab_hour, tab_matrix = st.tabs(
        ["By day of week", "By hour", "Day × hour heatmap"]
    )

    matrix = schedule_timing_matrix(filtered)
    days = day_of_week_totals(filtered)
    hours = hour_totals(filtered)
    value_col = VALUE_COL[metric]

    with tab_day:
        _bar_chart(
            days,
            "service_day",
            metric,
            f"{metric} by day of week",
            GREEN,
            "Day",
        )
        if not days.empty:
            best = days.loc[days[value_col].idxmax()]
            st.caption(
                f"Strongest day ({metric.lower()}): **{best['service_day']}** "
                f"({_format_value(metric, best[value_col])}, "
                f"{int(best['class_sessions'])} classes, {int(best['transactions'])} bookings)"
            )

    with tab_hour:
        _bar_chart(
            hours,
            "service_hour",
            metric,
            f"{metric} by hour of day",
            BLACK,
            "Hour (Malta)",
        )
        if not hours.empty:
            best = hours.loc[hours[value_col].idxmax()]
            st.caption(
                f"Peak hour ({metric.lower()}): **{int(best['service_hour']):02d}:00** "
                f"({_format_value(metric, best[value_col])}, "
                f"{int(best['class_sessions'])} classes, {int(best['transactions'])} bookings)"
            )

    with tab_matrix:
        _heatmap(matrix, value_col, f"{metric} by day and hour")
        with st.expander("Class session counts"):
            _heatmap(matrix, "class_sessions", "Class sessions by day and hour", currency=False)
