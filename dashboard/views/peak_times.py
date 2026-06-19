"""Class occupancy by day of week and hour (Momence Class Occupancy report)."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import (
    DAY_ORDER,
    filter_class_date_range,
    occupancy_day_totals,
    occupancy_hour_totals,
    occupancy_timing_matrix,
)
from dashboard.shared import (
    BLACK,
    CHART_HEIGHT,
    GREEN,
    GREEN_LIGHT,
    PLOTLY_CONFIG,
)

METRIC_OCCUPANCY = "Average occupancy %"
METRIC_BOOKINGS = "Total bookings"
METRIC_CHECKINS = "Total check-ins"
METRIC_CLASSES = "Class count"
METRIC_OPTIONS = [METRIC_OCCUPANCY, METRIC_BOOKINGS, METRIC_CHECKINS, METRIC_CLASSES]

METRIC_CONFIG: dict[str, tuple[str, str, str]] = {
    METRIC_OCCUPANCY: ("avg_occupancy", "Avg occupancy (%)", "percent"),
    METRIC_BOOKINGS: ("total_bookings", "Bookings", "count"),
    METRIC_CHECKINS: ("total_check_ins", "Check-ins", "count"),
    METRIC_CLASSES: ("class_sessions", "Classes", "count"),
}


def _format_value(metric: str, value: float) -> str:
    kind = METRIC_CONFIG[metric][2]
    if kind == "percent":
        return f"{value:.1f}%"
    return f"{int(value):,}"


def _heatmap(matrix: pd.DataFrame, value_col: str, title: str, kind: str) -> None:
    if matrix.empty:
        st.info("No class sessions in this range.")
        return

    hours = sorted(int(h) for h in matrix["class_hour"].unique())
    hour_labels = [f"{h:02d}:00" for h in hours]
    z_rows: list[list[float]] = []
    y_labels: list[str] = []

    for day in DAY_ORDER:
        row_vals: list[float] = []
        for hour in hours:
            match = matrix[(matrix["class_day"] == day) & (matrix["class_hour"] == hour)]
            val = float(match[value_col].iloc[0]) if not match.empty else 0.0
            row_vals.append(val)
        if any(v > 0 for v in row_vals):
            y_labels.append(day)
            z_rows.append(row_vals)

    if not z_rows:
        st.info("No class sessions in this range.")
        return

    z_max = max(max(row) for row in z_rows)
    if kind == "percent":
        hover = "%{y} %{x}<br>%{z:.1f}%<extra></extra>"
        colorbar_title = "%"
    else:
        hover = "%{y} %{x}<br>%{z:,.0f}<extra></extra>"
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
    if x_col == "class_hour":
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
    if kind == "percent":
        fig.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Peak Times")
    st.caption(
        "Class **occupancy and bookings** by schedule slot (Momence Class Occupancy report, Malta time). "
        "Each row is one class session — compare average occupancy % across days and hours."
    )

    if raw is None or raw.empty:
        st.warning("No class occupancy data found. Import ClassOccupancy CSVs into Supabase.")
        return

    filtered = filter_class_date_range(raw, start, end)
    if filtered.empty:
        st.warning("No class sessions in the selected date range.")
        return

    locations = sorted(filtered["location"].dropna().unique().tolist())
    location_options = ["All studios"] + locations
    location_pick = st.sidebar.selectbox(
        "Studio",
        options=location_options,
        key="peak_times_location",
    )
    if location_pick != "All studios":
        filtered = filtered[filtered["location"] == location_pick].copy()

    metric = st.sidebar.radio(
        "Compare by",
        options=METRIC_OPTIONS,
        horizontal=False,
        key="peak_times_metric",
    )

    class_sessions = len(filtered)
    total_bookings = int(filtered["bookings"].sum())
    total_check_ins = int(filtered["check_ins"].sum())
    avg_occ = float(filtered["occupancy_pct"].mean()) if class_sessions else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Class sessions", f"{class_sessions:,}")
    c2.metric("Total bookings", f"{total_bookings:,}")
    c3.metric("Total check-ins", f"{total_check_ins:,}")
    c4.metric("Avg occupancy", f"{avg_occ:.1f}%")

    tab_day, tab_hour, tab_matrix = st.tabs(
        ["By day of week", "By hour", "Day × hour heatmap"]
    )

    matrix = occupancy_timing_matrix(filtered)
    days = occupancy_day_totals(filtered)
    hours = occupancy_hour_totals(filtered)
    value_col, _, kind = METRIC_CONFIG[metric]

    with tab_day:
        _bar_chart(days, "class_day", metric, f"{metric} by day of week", GREEN, "Day")
        if not days.empty:
            best = days.loc[days[value_col].idxmax()]
            st.caption(
                f"Strongest day ({metric.lower()}): **{best['class_day']}** "
                f"({_format_value(metric, best[value_col])}, "
                f"{int(best['class_sessions'])} classes)"
            )

    with tab_hour:
        _bar_chart(
            hours, "class_hour", metric, f"{metric} by hour of day", BLACK, "Hour (Malta)"
        )
        if not hours.empty:
            best = hours.loc[hours[value_col].idxmax()]
            st.caption(
                f"Peak hour ({metric.lower()}): **{int(best['class_hour']):02d}:00** "
                f"({_format_value(metric, best[value_col])}, "
                f"{int(best['class_sessions'])} classes)"
            )

    with tab_matrix:
        _heatmap(matrix, value_col, f"{metric} by day and hour", kind)
        with st.expander("Class session counts"):
            _heatmap(matrix, "class_sessions", "Class sessions by day and hour", "count")
