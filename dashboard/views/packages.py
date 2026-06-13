"""Package and subscription popularity drill-down."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import item_breakdown
from dashboard.shared import BAR_CHART_HEIGHT, EUR, GREEN, GREEN_LIGHT, PLOTLY_CONFIG, filter_date_range

PACK_CATEGORY = "Pack"
SUB_CATEGORY = "Subscription"
PACK_COLOR = GREEN
SUB_COLOR = GREEN_LIGHT
CATEGORY_COLORS = {PACK_CATEGORY: PACK_COLOR, SUB_CATEGORY: SUB_COLOR}
CATEGORY_LABELS = {PACK_CATEGORY: "Package", SUB_CATEGORY: "Subscription"}


def _horizontal_bars(
    df: pd.DataFrame,
    title: str,
    value_col: str,
    value_label: str,
    color_by_category: bool,
) -> None:
    if df.empty:
        st.info("No sales in this category for the selected range.")
        return

    plot_df = df.sort_values(value_col, ascending=True)
    fig = go.Figure()

    if color_by_category:
        for category in plot_df["category"].unique():
            subset = plot_df[plot_df["category"] == category].sort_values(value_col, ascending=True)
            text = subset[value_col].map(
                lambda v: f"{v:,.0f}" if value_col == "sales_count" else EUR.format(v)
            )
            fig.add_trace(
                go.Bar(
                    x=subset[value_col],
                    y=subset["item"],
                    orientation="h",
                    name=CATEGORY_LABELS.get(category, category),
                    marker_color=CATEGORY_COLORS.get(category, PACK_COLOR),
                    text=text,
                    textposition="outside",
                )
            )
        fig.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    else:
        color = PACK_COLOR if plot_df["category"].iloc[0] == PACK_CATEGORY else SUB_COLOR
        fig.add_trace(
            go.Bar(
                x=plot_df[value_col],
                y=plot_df["item"],
                orientation="h",
                marker_color=color,
                text=plot_df[value_col].map(
                    lambda v: f"{v:,.0f}" if value_col == "sales_count" else EUR.format(v)
                ),
                textposition="outside",
                showlegend=False,
            )
        )

    left_margin = min(320, 40 + plot_df["item"].str.len().max() * 5)
    fig.update_layout(
        title=title,
        xaxis_title=value_label,
        height=max(BAR_CHART_HEIGHT, 80 + len(plot_df) * 36),
        margin=dict(l=left_margin, r=80, t=72 if color_by_category else 56, b=48),
        autosize=True,
        barmode="overlay",
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

    combined = pd.concat([packs, subs], ignore_index=True)

    if combined.empty:
        st.warning("No package or subscription sales in this date range.")
        return

    color_by_category = focus == "both"

    c1, c2, c3 = st.columns(3)
    with c1:
        _category_metrics(packs, "Package revenue")
    with c2:
        _category_metrics(subs, "Subscription revenue")
    with c3:
        st.metric("Total pack + sub sales", f"{int(combined['sales_count'].sum()):,}")

    tab_rev, tab_count = st.tabs(["By revenue", "By number sold"])
    with tab_rev:
        _horizontal_bars(
            combined,
            "Revenue by product",
            "net_sales",
            "Net sales (EUR)",
            color_by_category,
        )
    with tab_count:
        _horizontal_bars(
            combined,
            "Sales volume by product",
            "sales_count",
            "Number of sales",
            color_by_category,
        )

    with st.expander("Product detail table"):
        display = combined.copy()
        display["Type"] = display["category"].map(CATEGORY_LABELS)
        display["net_sales"] = display["net_sales"].map(lambda v: EUR.format(v))
        display = display.rename(
            columns={"item": "Product", "sales_count": "Sales", "net_sales": "Net sales"}
        ).drop(columns=["category"])
        display = display[["Type", "Product", "Sales", "Net sales"]]
        st.dataframe(display, use_container_width=True, hide_index=True)
