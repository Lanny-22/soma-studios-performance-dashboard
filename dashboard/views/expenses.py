"""Revolut expense tracking by label."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import expense_totals_by_label, filter_expense_date_range
from dashboard.shared import BAR_CHART_HEIGHT, BLACK, EUR, GREEN, PLOTLY_CONFIG


def _horizontal_bars(
    df: pd.DataFrame,
    title: str,
    value_col: str,
    value_label: str,
    color: str,
) -> None:
    if df.empty:
        st.info("No expenses in the selected date range.")
        return

    plot_df = df.sort_values(value_col, ascending=True)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df[value_col],
            y=plot_df["label"],
            orientation="h",
            marker_color=color,
            text=plot_df[value_col].map(
                lambda v: f"{v:,.0f}" if value_col == "transaction_count" else EUR.format(v)
            ),
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=value_label,
        yaxis_title="",
        height=BAR_CHART_HEIGHT,
        margin=dict(l=10, r=40, t=50, b=40),
        showlegend=False,
    )
    fig.update_yaxes(categoryorder="array", categoryarray=plot_df["label"].tolist())
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Expense Tracking")
    st.caption(
        "Spend from Revolut Business (`revolut_expenses`) — rows labelled in Revolut "
        "excluding `NOT_EXPENSE`. Filtered by transaction completed date (Malta time)."
    )

    if raw is None or raw.empty:
        st.warning("No expense data found in revolut_expenses.")
        return

    filtered = filter_expense_date_range(raw, start, end)
    if filtered.empty:
        st.warning("No expenses in the selected date range.")
        return

    by_label = expense_totals_by_label(filtered)
    total_spend = by_label["total_spend"].sum()
    total_count = int(by_label["transaction_count"].sum())
    label_count = len(by_label)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total spend", EUR.format(total_spend))
    c2.metric("Transactions", f"{total_count:,}")
    c3.metric("Expense labels", f"{label_count:,}")
    if total_count > 0:
        c4.metric("Average per transaction", EUR.format(total_spend / total_count))
    else:
        c4.metric("Average per transaction", EUR.format(0))

    tab_amount, tab_count = st.tabs(["By spend amount", "By transaction count"])
    with tab_amount:
        _horizontal_bars(
            by_label,
            "Total spend by label",
            "total_spend",
            "Spend (EUR)",
            GREEN,
        )
    with tab_count:
        _horizontal_bars(
            by_label,
            "Transaction count by label",
            "transaction_count",
            "Number of transactions",
            BLACK,
        )

    with st.expander("Label summary table"):
        display = by_label.copy()
        display["share_pct"] = (display["total_spend"] / total_spend * 100).round(1)
        display["total_spend"] = display["total_spend"].map(lambda v: EUR.format(v))
        display = display.rename(
            columns={
                "label": "Label",
                "transaction_count": "Transactions",
                "total_spend": "Total spend",
                "share_pct": "Share (%)",
            }
        )
        st.dataframe(display, use_container_width=True, hide_index=True)

    with st.expander("Transaction detail"):
        detail = filtered.sort_values("completed_at", ascending=False).copy()
        detail["completed_at"] = detail["completed_at"].dt.tz_convert("Europe/Malta").dt.strftime(
            "%Y-%m-%d %H:%M"
        )
        detail["spend"] = detail["spend"].map(lambda v: EUR.format(v))
        detail = detail.rename(
            columns={
                "completed_at": "Completed",
                "label": "Label",
                "description": "Description",
                "type": "Type",
                "product": "Account",
                "spend": "Spend",
            }
        )
        st.dataframe(
            detail[["Completed", "Label", "Description", "Type", "Account", "Spend"]],
            use_container_width=True,
            hide_index=True,
        )
