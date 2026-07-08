"""Weekly active member snapshots from Momence (Sunday counts by membership product)."""

from datetime import date
from typing import Any

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import (
    active_members_snapshot_totals,
    filter_active_member_snapshots,
)
from dashboard.shared import BAR_CHART_HEIGHT, GREEN, PLOTLY_CONFIG

SELECTED_SNAPSHOT_KEY = "active_members_selected_snapshot"


def _parse_snapshot_date(value: Any) -> date | None:
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


def _snapshot_from_selection(event: Any, snapshot_dates: list[date]) -> date | None:
    if event is None:
        return None
    selection = getattr(event, "selection", None)
    if selection is None:
        return None
    points = getattr(selection, "points", None) or []
    if not points:
        return None

    point = points[0]
    if isinstance(point, dict):
        raw = point.get("x") or point.get("customdata")
        idx = point.get("point_index")
    else:
        raw = getattr(point, "x", None) or getattr(point, "customdata", None)
        idx = getattr(point, "point_index", None)

    picked = _parse_snapshot_date(raw)
    if picked is not None:
        return picked
    if idx is not None and 0 <= idx < len(snapshot_dates):
        return snapshot_dates[idx]
    return None


def _store_snapshot_selection(snapshot: date | None, valid_dates: set[date]) -> None:
    if snapshot is not None and snapshot in valid_dates:
        st.session_state[SELECTED_SNAPSHOT_KEY] = snapshot


def _snapshot_detail_table(filtered: pd.DataFrame, snapshot: date) -> pd.DataFrame:
    rows = filtered[filtered["snapshot_date"] == snapshot].copy()
    if rows.empty:
        return pd.DataFrame(
            columns=["membership", "membership_type", "active_count", "is_presale"]
        )
    detail = (
        rows.groupby(["membership", "membership_type"], as_index=False)
        .agg(active_count=("active_count", "sum"), is_presale=("is_presale", "any"))
        .sort_values("active_count", ascending=False)
    )
    return detail


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Active Members")
    st.caption(
        "Weekly Momence active-member snapshots (typically Sundays). "
        "Totals sum **Active** counts across membership products in each export."
    )

    include_presale = st.toggle(
        "Include presale (3-credit packs)",
        value=True,
        help="When off, excludes memberships labelled PRE-SALE / PreSale (3-credit intro packs).",
    )

    filtered = filter_active_member_snapshots(
        raw, start, end, include_presale=include_presale
    )
    totals = active_members_snapshot_totals(filtered, include_presale=True)

    if totals.empty:
        st.warning("No active member snapshots in the selected date range.")
        return

    latest = totals.iloc[-1]
    peak_idx = totals["active_members"].idxmax()
    peak = totals.loc[peak_idx]

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Latest snapshot",
        f"{int(latest['active_members']):,}",
        help=f"On {latest['snapshot_date']}",
    )
    c2.metric(
        "Peak in range",
        f"{int(peak['active_members']):,}",
        help=f"On {peak['snapshot_date']}",
    )
    c3.metric("Snapshots in range", f"{len(totals):,}")

    snapshot_dates = totals["snapshot_date"].tolist()
    valid_dates = set(snapshot_dates)
    stored = st.session_state.get(SELECTED_SNAPSHOT_KEY)
    if stored not in valid_dates:
        st.session_state[SELECTED_SNAPSHOT_KEY] = snapshot_dates[-1]
    selected_snapshot = st.session_state[SELECTED_SNAPSHOT_KEY]

    labels = totals["active_members"].map(lambda v: f"{int(v):,}")
    snapshot_labels = [d.strftime("%d %b %Y") for d in snapshot_dates]
    fig = go.Figure(
        data=go.Bar(
            x=snapshot_labels,
            y=totals["active_members"],
            marker_color=GREEN,
            text=labels,
            textposition="outside",
            cliponaxis=False,
            customdata=snapshot_dates,
            hovertemplate="<b>%{x}</b><br>%{y:,} active<extra></extra>",
        )
    )
    presale_note = "incl. presale packs" if include_presale else "excl. presale packs"
    fig.update_layout(
        title=f"Active members per weekly snapshot ({presale_note})",
        xaxis_title="Snapshot date",
        yaxis_title="Active members",
        height=BAR_CHART_HEIGHT,
        margin=dict(l=48, r=24, t=56, b=48),
        autosize=True,
        clickmode="event+select",
    )
    fig.update_yaxes(tickformat=",d")
    event = st.plotly_chart(
        fig,
        use_container_width=True,
        config=PLOTLY_CONFIG,
        on_select="rerun",
        selection_mode="points",
        key="active_members_snapshot_chart",
    )
    picked = _snapshot_from_selection(event, snapshot_dates)
    _store_snapshot_selection(picked, valid_dates)
    selected_snapshot = st.session_state[SELECTED_SNAPSHOT_KEY]

    detail = _snapshot_detail_table(filtered, selected_snapshot)
    total_selected = int(detail["active_count"].sum()) if not detail.empty else 0
    st.subheader(f"Snapshot breakdown — {selected_snapshot:%d %b %Y}")
    st.caption(
        f"{total_selected:,} active members across {len(detail):,} membership products. "
        "Click a bar above to change snapshot."
    )
    st.dataframe(detail, use_container_width=True, hide_index=True)
