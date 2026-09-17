"""Membership cancellations over time and reason categories."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.data import (
    attach_cancellation_rates,
    cancellation_period_totals,
    cancellation_reason_breakdown,
    filter_cancellations,
)
from dashboard.shared import BAR_CHART_HEIGHT, CHART_HEIGHT, DAY_MS, GREEN, PLOTLY_CONFIG

REF_LINE = "rgba(27, 27, 27, 0.2)"
GRANULARITIES = ("Daily", "Weekly", "Monthly")
METRIC_MODES = ("Count", "Rate")
SELECTED_PERIOD_KEY = "cancellations_selected_period"
GRANULARITY_PREV_KEY = "cancellations_granularity_prev"

CATEGORY_COLORS = {
    "Travel / away": "#2d6a4f",
    "Cost / affordability": "#40916c",
    "Too busy / schedule": "#74c69d",
    "Switching membership": "#95d5b2",
    "Other / unspecified": "#1b1b1b",
}


def _bar_width_ms(granularity: str) -> float:
    if granularity == "Weekly":
        return DAY_MS * 6.5
    if granularity == "Monthly":
        return DAY_MS * 26
    return DAY_MS * 0.92


def _period_noun(granularity: str) -> str:
    return {"Daily": "day", "Weekly": "week", "Monthly": "month"}[granularity]


def _parse_period_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    try:
        return pd.to_datetime(value).date()
    except (TypeError, ValueError):
        return None


def _period_start_for_row(cancel_date: date, granularity: str) -> date:
    ts = pd.Timestamp(cancel_date)
    grain = (granularity or "Daily").strip().lower()
    if grain == "weekly":
        return ts.to_period("W-SUN").start_time.date()
    if grain == "monthly":
        return ts.to_period("M").start_time.date()
    return cancel_date


def _rows_for_period(
    filtered: pd.DataFrame,
    period_start: date,
    granularity: str,
) -> pd.DataFrame:
    if filtered.empty:
        return filtered
    work = filtered.copy()
    work["_period_start"] = work["cancel_date"].map(
        lambda d: _period_start_for_row(d, granularity)
    )
    return work[work["_period_start"] == period_start].drop(columns=["_period_start"])


def _apply_chart_selection(event: Any, period_starts: list[date]) -> None:
    """Update session when a bar is clicked; ignore empty first-load selection."""
    if event is None or not hasattr(event, "selection"):
        return
    points = getattr(event.selection, "points", None) or []
    if not points:
        return

    point = points[0]
    if isinstance(point, dict):
        raw = point.get("customdata")
        if isinstance(raw, (list, tuple)) and raw:
            raw = raw[0]
        if raw is None:
            raw = point.get("x")
        idx = point.get("point_index")
        if idx is None:
            idx = point.get("pointNumber")
    else:
        raw = getattr(point, "customdata", None)
        if isinstance(raw, (list, tuple)) and raw:
            raw = raw[0]
        if raw is None:
            raw = getattr(point, "x", None)
        idx = getattr(point, "point_index", None)
        if idx is None:
            idx = getattr(point, "point_number", None)

    picked = _parse_period_date(raw)
    if picked is None and idx is not None and 0 <= idx < len(period_starts):
        picked = period_starts[idx]
    if picked is not None:
        st.session_state[SELECTED_PERIOD_KEY] = picked


def _metric_row_count(
    period: pd.DataFrame,
    total: int,
    start: date,
    end: date,
    granularity: str,
) -> None:
    calendar_days = max((end - start).days + 1, 1)
    noun = _period_noun(granularity)
    peak_idx = period["cancellations"].idxmax()
    peak_label = period.loc[peak_idx, "period_label"]
    peak_val = int(period.loc[peak_idx, "cancellations"])
    avg_period = total / max(len(period), 1)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cancellations (filtered)", f"{total:,}")
    c2.metric(
        f"Peak {noun}",
        f"{peak_val:,}",
        help=f"Most cancellations in {peak_label}",
    )
    c3.metric(
        f"Average per {noun}",
        f"{avg_period:.2f}",
        help=f"Cancellations ÷ {len(period)} {noun}s with activity",
    )
    c4.metric(
        f"{noun.capitalize()}s with cancellations",
        f"{len(period):,}",
        help=f"Across {calendar_days} calendar days in range",
    )


def _metric_row_rate(period: pd.DataFrame, total: int, granularity: str) -> None:
    noun = _period_noun(granularity)
    rated = period.dropna(subset=["cancellation_rate", "active_members"])
    if rated.empty:
        st.warning(
            "No active-subscription snapshots available to calculate cancellation rate "
            "for this range."
        )
        return

    overall_active = float(rated["active_members"].mean())
    overall_rate = total / overall_active if overall_active else None
    peak_idx = rated["cancellation_rate"].idxmax()
    peak_label = rated.loc[peak_idx, "period_label"]
    peak_rate = float(rated.loc[peak_idx, "cancellation_rate"])
    peak_active = rated.loc[peak_idx, "active_members"]
    avg_rate = float(rated["cancellation_rate"].mean())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Overall rate",
        f"{overall_rate:.1%}" if overall_rate is not None else "—",
        help=(
            f"{total:,} cancellations ÷ {overall_active:.0f} avg active subscriptions "
            f"across {noun}s with snapshot data"
        ),
    )
    c2.metric(
        f"Peak {noun} rate",
        f"{peak_rate:.1%}",
        help=f"{peak_label} ({int(rated.loc[peak_idx, 'cancellations'])} ÷ {peak_active:.0f})",
    )
    c3.metric(
        f"Average {noun} rate",
        f"{avg_rate:.1%}",
        help=f"Mean of {noun}ly rates in range",
    )
    c4.metric(
        f"{noun.capitalize()}s with rate",
        f"{len(rated):,}",
        help=f"Of {len(period):,} {noun}s with cancellations",
    )


def _period_chart(
    period: pd.DataFrame,
    granularity: str,
    *,
    show_rate: bool,
) -> None:
    if show_rate:
        chart = period.dropna(subset=["cancellation_rate"]).copy()
        if chart.empty:
            st.info("No periods with both cancellations and active-member data.")
            return
        y = chart["cancellation_rate"] * 100
        avg_y = float(y.mean())
        max_y = float(y.max())
        text = y.map(lambda v: f"{v:.1f}%")
        hover_labels = chart.apply(
            lambda r: (
                f"{r['period_label']}<br>{int(r['cancellations'])} cancellations "
                f"/ {r['active_members']:.0f} subscriptions"
            ),
            axis=1,
        )
        hover = "%{customdata[1]}<br>Rate: %{y:.1f}%<extra></extra>"
        title = f"{granularity} cancellation rate"
        y_title = "Cancellation rate (%)"
        yaxis_kwargs = dict(ticksuffix="%", tickformat=".1f")
    else:
        chart = period.copy()
        y = chart["cancellations"]
        avg_y = float(y.mean())
        max_y = float(y.max())
        text = y.map(lambda v: f"{int(v)}")
        hover_labels = chart["period_label"]
        hover = "%{customdata[1]}<br>%{y} cancellations<extra></extra>"
        title = f"{granularity} cancellations"
        y_title = "Cancellations"
        yaxis_kwargs = dict(tickformat=",.0f", dtick=1 if max_y <= 10 else None)

    period_starts = chart["period_start"].tolist()
    custom = [[start, label] for start, label in zip(period_starts, hover_labels)]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart["period_start"],
            y=y,
            customdata=custom,
            name=title,
            marker_color=GREEN,
            width=_bar_width_ms(granularity),
            text=text,
            textposition="outside",
            textangle=-90 if granularity == "Daily" else 0,
            cliponaxis=False,
            hovertemplate=hover,
        )
    )
    fig.add_hline(y=max_y, line_dash="dot", line_color=REF_LINE, line_width=2.5)
    fig.add_hline(y=avg_y, line_dash="dot", line_color=REF_LINE, line_width=2.5)
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title=y_title,
        height=CHART_HEIGHT,
        margin=dict(l=48, r=24, t=80, b=48),
        hovermode="closest",
        autosize=True,
        bargap=0.12 if granularity != "Daily" else 0.06,
        uniformtext_minsize=8,
        uniformtext_mode="hide",
        clickmode="event+select",
    )
    if granularity == "Monthly":
        fig.update_xaxes(dtick="M1", tickformat="%b %Y")
    elif granularity == "Weekly":
        fig.update_xaxes(tickformat="%d %b")
    fig.update_yaxes(**yaxis_kwargs)

    event = st.plotly_chart(
        fig,
        use_container_width=True,
        config=PLOTLY_CONFIG,
        on_select="rerun",
        selection_mode="points",
        key=f"cancellations_period_chart_{granularity}_{'rate' if show_rate else 'count'}",
    )
    _apply_chart_selection(event, period_starts)


def _category_chart(breakdown: pd.DataFrame, title: str = "Cancellation reasons") -> None:
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
        title=title,
        xaxis_title="Category",
        yaxis_title="Cancellations",
        height=BAR_CHART_HEIGHT,
        margin=dict(l=48, r=24, t=80, b=80),
        autosize=True,
        showlegend=False,
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _reason_samples(rows: pd.DataFrame) -> None:
    with st.expander("Sample raw reasons by category"):
        for category in rows["reason_category"].dropna().unique():
            sample = (
                rows.loc[rows["reason_category"] == category, "reason"]
                .fillna("")
                .replace("", "(blank)")
                .value_counts()
                .head(5)
            )
            st.markdown(f"**{category}**")
            for reason, count in sample.items():
                st.caption(f"{count}× — {reason}")


def _detail_table(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(
            columns=["cancel_date", "membership", "reason_category", "reason"]
        )
    detail = rows[["cancel_date", "membership", "reason_category", "reason"]].copy()
    detail = detail.sort_values(["cancel_date", "membership"], ascending=[False, True])
    detail["reason"] = detail["reason"].fillna("").replace("", "(blank)")
    return detail.reset_index(drop=True)


def render(
    raw: pd.DataFrame,
    start: date,
    end: date,
    active_members: pd.DataFrame | None = None,
) -> None:
    st.title("Cancellations")
    st.caption(
        "Momence membership cancellations by cancel date. "
        "Reasons are grouped from the Momence **Reason** field (including free-text notes). "
        "Click a bar to inspect that period; clear the selection to return to the full range."
    )

    filtered = filter_cancellations(raw, start, end)
    if filtered.empty:
        st.warning("No cancellations in the selected date range.")
        return

    c1, c2 = st.columns(2)
    with c1:
        granularity = st.radio(
            "Time aggregation",
            GRANULARITIES,
            horizontal=True,
            index=0,
            key="cancellations_granularity",
            help="Group the trend chart by day, week (Mon–Sun), or calendar month.",
        )
    with c2:
        metric_mode = st.radio(
            "Metric",
            METRIC_MODES,
            horizontal=True,
            index=0,
            key="cancellations_metric_mode",
            help=(
                "Rate = cancellations ÷ active Subscriptions from Momence Active Members "
                "snapshots (membership_type = Subscription only; excludes class packs). "
                "Weekly uses the snapshot in that week; monthly averages snapshots in the month."
            ),
        )

    if st.session_state.get(GRANULARITY_PREV_KEY) != granularity:
        st.session_state[SELECTED_PERIOD_KEY] = None
        st.session_state[GRANULARITY_PREV_KEY] = granularity

    show_rate = metric_mode == "Rate"
    if show_rate and granularity == "Daily":
        st.caption(
            "Daily rate uses the latest Active Subscriptions snapshot on or before that day."
        )

    period = cancellation_period_totals(filtered, granularity)
    period = attach_cancellation_rates(period, active_members, granularity)
    valid_periods = set(period["period_start"].tolist())
    stored = st.session_state.get(SELECTED_PERIOD_KEY)
    if stored is not None and stored not in valid_periods:
        st.session_state[SELECTED_PERIOD_KEY] = None

    total = int(len(filtered))
    if show_rate:
        _metric_row_rate(period, total, granularity)
    else:
        _metric_row_count(period, total, start, end, granularity)

    _period_chart(
        period,
        granularity,
        show_rate=show_rate,
    )
    selected_period = st.session_state.get(SELECTED_PERIOD_KEY)

    if selected_period is not None:
        if st.button("Clear bar selection", key="cancellations_clear_selection"):
            st.session_state[SELECTED_PERIOD_KEY] = None
            st.rerun()

        detail_rows = _rows_for_period(filtered, selected_period, granularity)
        label_rows = period[period["period_start"] == selected_period]
        period_label = (
            str(label_rows.iloc[0]["period_label"])
            if not label_rows.empty
            else str(selected_period)
        )
        st.subheader(f"Selected period — {period_label}")
        st.caption(
            f"{len(detail_rows):,} cancellations in this {_period_noun(granularity)}. "
            "Clear the selection to show the full date range again."
        )
        if detail_rows.empty:
            st.info("No cancellation rows for this bar.")
            return

        breakdown = cancellation_reason_breakdown(detail_rows)
        _category_chart(breakdown, title=f"Reasons — {period_label}")
        st.dataframe(_detail_table(detail_rows), use_container_width=True, hide_index=True)
        _reason_samples(detail_rows)
        return

    breakdown = cancellation_reason_breakdown(filtered)
    st.subheader("Why people cancel")
    st.caption(
        "Full selected date range. Categories are rule-based from Reason text: "
        "Travel / away, Cost, Too busy, Switching membership, and Other. "
        "Click a bar above to drill into one period."
    )
    _category_chart(breakdown)
    _reason_samples(filtered)
