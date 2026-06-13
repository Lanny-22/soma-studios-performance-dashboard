"""Product sales drill-down."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import item_breakdown
from dashboard.shared import BAR_CHART_HEIGHT, EUR, GREEN, PLOTLY_CONFIG, filter_date_range, operating_view_banner

PRODUCT_CATEGORY = "Product"


def _horizontal_bars(
    df: pd.DataFrame,
    title: str,
    value_col: str,
    value_label: str,
) -> None:
    if df.empty:
        st.info("No product sales in the selected range.")
        return

    plot_df = df.sort_values(value_col, ascending=True)
    y_order = plot_df["item"].tolist()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df[value_col],
            y=plot_df["item"],
            orientation="h",
            marker_color=GREEN,
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
        margin=dict(l=left_margin, r=80, t=56, b=48),
        autosize=True,
        yaxis=dict(categoryorder="array", categoryarray=y_order),
    )
    if value_col == "net_sales":
        fig.update_xaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Product Sales")
    operating_view_banner()
    st.caption("Retail and merch — which products sell most in the selected period")

    filtered = filter_date_range(raw, start, end)
    products = item_breakdown(filtered, [PRODUCT_CATEGORY])

    if products.empty:
        st.warning("No product sales in this date range.")
        return

    total_revenue = products["net_sales"].sum()
    total_units = int(products["sales_count"].sum())
    top = products.iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Product revenue", EUR.format(total_revenue))
    c2.metric("Units sold", f"{total_units:,}")
    c3.metric(
        "Top product",
        top["item"],
        help=f"{int(top['sales_count']):,} sold · {EUR.format(top['net_sales'])} revenue",
    )

    tab_rev, tab_count = st.tabs(["By revenue", "By number sold"])
    with tab_rev:
        _horizontal_bars(products, "Product revenue", "net_sales", "Net sales (EUR)")
    with tab_count:
        _horizontal_bars(products, "Product sales volume", "sales_count", "Number of sales")

    with st.expander("Product detail table"):
        display = products.copy()
        display["net_sales"] = display["net_sales"].map(lambda v: EUR.format(v))
        display = display.rename(
            columns={"item": "Product", "sales_count": "Sales", "net_sales": "Net sales"}
        ).drop(columns=["category"])
        st.dataframe(display, use_container_width=True, hide_index=True)
