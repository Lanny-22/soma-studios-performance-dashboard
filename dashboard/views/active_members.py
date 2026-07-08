"""Weekly active member snapshots from Momence (Sunday counts by membership product)."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import (
    active_members_snapshot_totals,
    filter_active_member_snapshots,
)
from dashboard.shared import BAR_CHART_HEIGHT, BLACK, GREEN, PLOTLY_CONFIG


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

    labels = totals["active_members"].map(lambda v: f"{int(v):,}")
    fig = go.Figure(
        data=go.Bar(
            x=totals["snapshot_date"],
            y=totals["active_members"],
            marker_color=GREEN,
            text=labels,
            textposition="outside",
            cliponaxis=False,
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
    )
    fig.update_yaxes(tickformat=",d")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    with st.expander("Snapshot detail"):
        detail = (
            filtered.groupby(["snapshot_date", "membership", "membership_type"], as_index=False)
            .agg(active_count=("active_count", "sum"), is_presale=("is_presale", "any"))
            .sort_values(["snapshot_date", "active_count"], ascending=[True, False])
        )
        st.dataframe(detail, use_container_width=True, hide_index=True)
