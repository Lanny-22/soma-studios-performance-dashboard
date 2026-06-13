"""Password-protected SOMA Studios sales analytics (Streamlit)."""

import hmac
from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import daily_totals, filter_sales, load_total_sales
from src.config import get_settings

st.set_page_config(
    page_title="SOMA Studios — Sales",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

EUR = "€{:,.2f}"


def _password_gate() -> bool:
    settings = get_settings()
    expected = settings.dashboard_password
    if not expected:
        st.error("Set DASHBOARD_PASSWORD in your .env file before opening the dashboard.")
        st.stop()

    if st.session_state.get("authenticated"):
        return True

    st.markdown("## SOMA Studios Analytics")
    st.caption("Enter the password to view sales data.")
    entered = st.text_input("Password", type="password", key="password_input")
    if st.button("Sign in", type="primary"):
        if hmac.compare_digest(entered, expected):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


def _metric_row(total: float, transactions: int, days: int) -> None:
    avg_daily = total / days if days else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Net sales", EUR.format(total))
    c2.metric("Transactions", f"{transactions:,}")
    c3.metric("Avg daily sales", EUR.format(avg_daily))


def _daily_chart(daily: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=daily["sale_date"],
            y=daily["net_sales"],
            name="Daily net sales",
            marker_color="#2d6a4f",
        )
    )
    fig.update_layout(
        title="Daily net sales",
        xaxis_title="Date",
        yaxis_title="Net sales (EUR)",
        height=420,
        margin=dict(l=40, r=20, t=50, b=40),
        hovermode="x unified",
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)


def _cumulative_chart(daily: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily["sale_date"],
            y=daily["cumulative_sales"],
            mode="lines+markers",
            name="Cumulative net sales",
            line=dict(color="#40916c", width=3),
            marker=dict(size=6),
        )
    )
    fig.update_layout(
        title="Cumulative net sales",
        xaxis_title="Date",
        yaxis_title="Cumulative net sales (EUR)",
        height=420,
        margin=dict(l=40, r=20, t=50, b=40),
        hovermode="x unified",
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True)


@st.cache_data(ttl=300, show_spinner="Loading sales from Supabase…")
def _cached_sales():
    return load_total_sales()


def main() -> None:
    if not _password_gate():
        return

    st.title("Total Sales")
    st.caption("Momence Total Sales report · April & May 2026")

    if st.sidebar.button("Sign out"):
        st.session_state.authenticated = False
        st.rerun()

    raw = _cached_sales()
    if raw.empty:
        st.warning("No sales data found in momence_total_sales.")
        return

    min_date = raw["sale_date"].min()
    max_date = raw["sale_date"].max()
    all_categories = sorted(raw["category"].unique())

    st.sidebar.header("Filters")

    month_key = st.sidebar.radio(
        "Month",
        options=["all", "april", "may"],
        format_func=lambda k: {
            "all": "April + May",
            "april": "April only",
            "may": "May only",
        }[k],
        horizontal=True,
    )

    if month_key == "april":
        range_min, range_max = date(2026, 4, 1), date(2026, 4, 30)
    elif month_key == "may":
        range_min, range_max = date(2026, 5, 1), date(2026, 5, 31)
    else:
        range_min, range_max = min_date, max_date

    start, end = st.sidebar.date_input(
        "Date range",
        value=(range_min, range_max),
        min_value=min_date,
        max_value=max_date,
        key=f"date_range_{month_key}",
    )
    if not isinstance(start, date):
        start, end = start[0], start[1]

    selected_categories = st.sidebar.multiselect(
        "Product type (category)",
        options=all_categories,
        default=all_categories,
        help="Momence category: Pack, Class, Product, Subscription, etc.",
    )

    filtered = filter_sales(raw, selected_categories, month_key, start, end)
    daily = daily_totals(filtered)

    if filtered.empty:
        st.warning("No rows match the current filters.")
        return

    total = filtered["net_sales"].sum()
    transactions = len(filtered)
    days = daily["sale_date"].nunique()
    _metric_row(total, transactions, days)

    col1, col2 = st.columns(2)
    with col1:
        _daily_chart(daily)
    with col2:
        _cumulative_chart(daily)

    with st.expander("Category breakdown"):
        breakdown = (
            filtered.groupby("category", as_index=False)
            .agg(net_sales=("net_sales", "sum"), count=("sale_reference", "count"))
            .sort_values("net_sales", ascending=False)
        )
        breakdown["net_sales"] = breakdown["net_sales"].map(lambda v: EUR.format(v))
        st.dataframe(breakdown, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()