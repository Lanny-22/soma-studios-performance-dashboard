"""Revolut expense tracking by label."""

from datetime import date
from typing import Any

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import expense_totals_by_label, filter_expense_date_range
from dashboard.shared import BAR_CHART_HEIGHT, BLACK, EUR, GREEN, PLOTLY_CONFIG

SELECTED_LABEL_KEY = "expense_selected_label"


def _label_from_selection(event: Any) -> str | None:
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
        label = point.get("y") or point.get("customdata")
        if isinstance(label, (list, tuple)):
            label = label[0]
        return str(label) if label else None

    label = getattr(point, "y", None) or getattr(point, "customdata", None)
    if isinstance(label, (list, tuple)):
        label = label[0]
    return str(label) if label else None


def _store_label_selection(label: str | None, valid_labels: set[str]) -> None:
    if label and label in valid_labels:
        st.session_state[SELECTED_LABEL_KEY] = label


def _horizontal_bars(
    df: pd.DataFrame,
    title: str,
    value_col: str,
    value_label: str,
    color: str,
    chart_key: str,
    valid_labels: set[str],
) -> None:
    if df.empty:
        st.info("No expenses in the selected date range.")
        return

    plot_df = df.sort_values(value_col, ascending=True)
    label_order = plot_df["label"].tolist()
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df[value_col],
            y=plot_df["label"],
            orientation="h",
            marker_color=color,
            customdata=plot_df["label"],
            text=plot_df[value_col].map(
                lambda v: f"{v:,.0f}" if value_col == "transaction_count" else EUR.format(v)
            ),
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=value_label,
        yaxis_title="",
        height=BAR_CHART_HEIGHT,
        margin=dict(l=10, r=40, t=50, b=40),
        showlegend=False,
        clickmode="event+select",
    )
    fig.update_yaxes(categoryorder="array", categoryarray=plot_df["label"].tolist())
    event = st.plotly_chart(
        fig,
        use_container_width=True,
        config=PLOTLY_CONFIG,
        on_select="rerun",
        selection_mode="points",
        key=chart_key,
    )
    label = _label_from_selection(event)
    if label is None and event is not None:
        selection = getattr(event, "selection", None)
        points = getattr(selection, "points", None) or []
        if points:
            point = points[0]
            idx = point.get("point_index") if isinstance(point, dict) else getattr(point, "point_index", None)
            if idx is not None and 0 <= idx < len(label_order):
                label = label_order[idx]
    _store_label_selection(label, valid_labels)


def _transaction_table(label_rows: pd.DataFrame) -> None:
    detail = label_rows.copy()
    detail["completed_at"] = detail["completed_at"].dt.tz_convert("Europe/Malta").dt.strftime(
        "%Y-%m-%d %H:%M"
    )
    detail["amount"] = detail["amount"].map(lambda v: EUR.format(v))
    detail["fee"] = detail["fee"].map(lambda v: EUR.format(v))
    detail["spend"] = detail["spend"].map(lambda v: EUR.format(v))
    if "notes" in detail.columns:
        detail["notes"] = detail["notes"].fillna("")

    detail = detail.rename(
        columns={
            "completed_at": "Completed",
            "description": "Description",
            "type": "Type",
            "product": "Account",
            "amount": "Amount",
            "fee": "Fee",
            "spend": "Spend",
            "currency": "Currency",
            "notes": "Notes",
        }
    )
    st.dataframe(
        detail[
            [
                "Completed",
                "Description",
                "Type",
                "Account",
                "Amount",
                "Fee",
                "Spend",
                "Currency",
                *(["Notes"] if "Notes" in detail.columns else []),
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Expense Tracking")
    st.caption(
        "Spend from Revolut Business (`revolut_expenses`) — rows labelled in Revolut "
        "excluding `NOT_EXPENSE`. Filtered by transaction completed date (Malta time). "
        "Click a label in the chart to see its transactions."
    )

    if raw is None or raw.empty:
        st.warning("No expense data found in revolut_expenses.")
        return

    filtered = filter_expense_date_range(raw, start, end)
    if filtered.empty:
        st.warning("No expenses in the selected date range.")
        return

    by_label = expense_totals_by_label(filtered)
    valid_labels = set(by_label["label"])
    if st.session_state.get(SELECTED_LABEL_KEY) not in valid_labels:
        st.session_state[SELECTED_LABEL_KEY] = None

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
            "Total spend by label — click a bar to drill down",
            "total_spend",
            "Spend (EUR)",
            GREEN,
            "expense_chart_spend",
            valid_labels,
        )
    with tab_count:
        _horizontal_bars(
            by_label,
            "Transaction count by label — click a bar to drill down",
            "transaction_count",
            "Number of transactions",
            BLACK,
            "expense_chart_count",
            valid_labels,
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
        table_event = st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="expense_label_table",
        )
        rows = getattr(getattr(table_event, "selection", None), "rows", None) or []
        if rows:
            row_idx = rows[0]
            _store_label_selection(display.iloc[row_idx]["Label"], valid_labels)

    selected_label = st.session_state.get(SELECTED_LABEL_KEY)
    st.subheader("Transactions by label")

    if not selected_label:
        st.info("Click a label bar in the chart above (or a row in the summary table) to list its transactions.")
        return

    label_rows = filtered[filtered["label"] == selected_label].sort_values(
        "completed_at", ascending=False
    )
    label_spend = label_rows["spend"].sum()
    label_count = len(label_rows)

    st.markdown(f"**{selected_label}**")
    c1, c2 = st.columns(2)
    c1.metric("Label spend (in range)", EUR.format(label_spend))
    c2.metric("Transactions", f"{label_count:,}")

    _transaction_table(label_rows)
