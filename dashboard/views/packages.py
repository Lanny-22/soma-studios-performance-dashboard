"""Package and subscription popularity drill-down."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import item_breakdown
from dashboard.shared import BAR_CHART_HEIGHT, EUR, GREEN, PLOTLY_CONFIG, filter_date_range

PACK_CATEGORY = "Pack"
SUB_CATEGORY = "Subscription"


def _horizontal_bars(
    df: pd.DataFrame,
    title: str,
    value_col: str,
    value_label: str,
) -> None:
    if df.empty:
        st.info("No sales in this category for the selected range.")
        return

    plot_df = df.sort_values(value_col, ascending=True)
    fig = go.Figure(
        go.Bar(
            x=plot_df[value_col],
            y=plot_df["item"],
            orientation="h",
            marker_color=GREEN,
            text=plot_df[value_col].map(lambda v: f"{v:,.0f}" if value_col == "sales_count" else EUR.format(v)),
            textposition="outside",
        )
    )
    left_margin = min(320, 40 + plot_df["item"].str.len().max() * 5)
    fig.update_layout(
        title=title,
        xaxis_title=value_label,
        height=max(BAR_CHART_HEIGHT, 80 + len(plot_df) * 36),
        margin=dict(l=left_margin, r=80, t=56, b=48),
        autosize=True,
    )
    if value_col == "net_sales":
        fig.update_xaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _category_metrics(df: pd.DataFrame, label: str) -> None:
    if df.empty:
        st.metric(label, "—")
        return
    total = df["net_sales"].sum()
    count = int(df["sales_count"].sum())
    top = df.iloc[0]
    st.metric(
        label,
        EUR.format(total),
        help=f"{count:,} sales · top: {top['item']}",
    )


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Packages & Subscriptions")
    st.caption("Which packs and memberships sell most in the selected period")

    focus = st.sidebar.radio(
        "Focus",
        options=["both", "pack", "subscription"],
        format_func=lambda k: {
            "both": "Packages + Subscriptions",
            "pack": "Packages only",
            "subscription": "Subscriptions only",
        }[k],
        horizontal=True,
    )

    filtered = filter_date_range(raw, start, end)
    packs = item_breakdown(filtered, [PACK_CATEGORY])
    subs = item_breakdown(filtered, [SUB_CATEGORY])

    if focus == "pack":
        subs = subs.iloc[0:0]
    elif focus == "subscription":
        packs = packs.iloc[0:0]

    if packs.empty and subs.empty:
        st.warning("No package or subscription sales in this date range.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        _category_metrics(packs, "Package revenue")
    with c2:
        _category_metrics(subs, "Subscription revenue")
    with c3:
        combined_count = int(packs["sales_count"].sum() + subs["sales_count"].sum())
        st.metric("Total pack + sub sales", f"{combined_count:,}")

    if not packs.empty and focus in ("both", "pack"):
        st.subheader("Packages")
        tab_rev, tab_count = st.tabs(["By revenue", "By number sold"])
        with tab_rev:
            _horizontal_bars(packs, "Package revenue by product", "net_sales", "Net sales (EUR)")
        with tab_count:
            _horizontal_bars(packs, "Package sales volume", "sales_count", "Number of sales")

        with st.expander("Package detail table"):
            display = packs.copy()
            display["net_sales"] = display["net_sales"].map(lambda v: EUR.format(v))
            display = display.rename(columns={"item": "Package", "sales_count": "Sales", "net_sales": "Net sales"})
            st.dataframe(display, use_container_width=True, hide_index=True)

    if not subs.empty and focus in ("both", "subscription"):
        st.subheader("Subscriptions")
        tab_rev, tab_count = st.tabs(["By revenue", "By number sold"])
        with tab_rev:
            _horizontal_bars(subs, "Subscription revenue by plan", "net_sales", "Net sales (EUR)")
        with tab_count:
            _horizontal_bars(subs, "Subscription sales volume", "sales_count", "Number of sales")

        with st.expander("Subscription detail table"):
            display = subs.copy()
            display["net_sales"] = display["net_sales"].map(lambda v: EUR.format(v))
            display = display.rename(
                columns={"item": "Subscription", "sales_count": "Sales", "net_sales": "Net sales"}
            )
            st.dataframe(display, use_container_width=True, hide_index=True)
