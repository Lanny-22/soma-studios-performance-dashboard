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
CHART_HEIGHT = 620
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}


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


def _metric_row(
    daily: pd.DataFrame,
    total: float,
    transactions: int,
    start: date,
    end: date,
) -> None:
    calendar_days = max((end - start).days + 1, 1)
    avg_daily = total / calendar_days

    best_idx = daily["net_sales"].idxmax()
    best_date = daily.loc[best_idx, "sale_date"]
    best_val = float(daily.loc[best_idx, "net_sales"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net sales (filtered)", EUR.format(total), help=f"{transactions:,} transactions")
    c2.metric(
        "Best single day",
        EUR.format(best_val),
        help=f"Peak net sales on {best_date}",
    )
    c3.metric(
        "Average daily sales",
        EUR.format(avg_daily),
        help=f"Net sales ÷ {calendar_days} days in selected range",
    )
    c4.metric("Days with sales", f"{len(daily):,}", help=f"Out of {calendar_days} days in range")


DAY_MS = 24 * 60 * 60 * 1000


def _daily_chart(daily: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=daily["sale_date"],
            y=daily["net_sales"],
            name="Daily net sales",
            marker_color="#2d6a4f",
            width=DAY_MS * 0.92,
        )
    )
    fig.update_layout(
        title="Daily net sales",
        xaxis_title="Date",
        yaxis_title="Net sales (EUR)",
        height=CHART_HEIGHT,
        margin=dict(l=48, r=24, t=56, b=48),
        hovermode="x unified",
        autosize=True,
        bargap=0.06,
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _cumulative_chart(daily: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily["sale_date"],
            y=daily["cumulative_sales"],
            mode="lines+markers",
            name="Cumulative net sales",
            line=dict(color="#40916c", width=3),
            marker=dict(size=8),
        )
    )

    last = daily.iloc[-1]
    final_date = last["sale_date"]
    final_val = float(last["cumulative_sales"])
    label = EUR.format(final_val)

    fig.add_trace(
        go.Scatter(
            x=[final_date],
            y=[final_val],
            mode="markers",
            name="Final total",
            marker=dict(size=14, color="#2d6a4f", line=dict(width=2, color="#ffffff")),
            showlegend=False,
            hovertemplate=f"{final_date}<br>Cumulative: {label}<extra></extra>",
        )
    )
    fig.add_annotation(
        x=final_date,
        y=final_val,
        text=label,
        showarrow=True,
        arrowhead=2,
        arrowsize=1.2,
        arrowwidth=1.5,
        arrowcolor="#40916c",
        ax=50,
        ay=-48,
        bgcolor="rgba(255, 255, 255, 0.95)",
        bordercolor="#40916c",
        borderwidth=1,
        borderpad=6,
        font=dict(size=14, color="#1b1b1b"),
    )

    fig.update_layout(
        title="Cumulative net sales",
        xaxis_title="Date",
        yaxis_title="Cumulative net sales (EUR)",
        height=CHART_HEIGHT,
        margin=dict(l=48, r=24, t=56, b=48),
        hovermode="x unified",
        autosize=True,
    )
    fig.update_yaxes(tickformat=",.0f")
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


@st.cache_data(ttl=300, show_spinner="Loading sales from Supabase…")
def _cached_sales():
    return load_total_sales()


def main() -> None:
    if not _password_gate():
        return

    st.title("Total Sales")
    st.caption("Momence Total Sales · filtered view")

    if st.sidebar.button("Sign out"):
        st.session_state.authenticated = False
        st.rerun()

    try:
        raw = _cached_sales()
    except Exception as exc:
        err = str(exc)
        st.error("Could not connect to Supabase.")
        if "authentication failures" in err or "CIRCUITBREAKER" in err:
            st.warning(
                "Supabase blocked connections after repeated **wrong database password** attempts. "
                "Stop the app (Reboot), wait 2 minutes, then fix **DATABASE_URL** in Streamlit secrets — "
                "it must be your **Supabase database password** (from .env), not your dashboard login password."
            )
        else:
            st.caption("Check DATABASE_URL in Streamlit secrets.")
        with st.expander("Technical details"):
            st.code(err)
        return
    if raw.empty:
        st.warning("No sales data found in momence_total_sales.")
        return

    min_date = raw["sale_date"].min()
    max_date = raw["sale_date"].max()
    all_categories = sorted(raw["category"].unique())

    st.sidebar.header("Filters")

    start, end = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if not isinstance(start, date):
        start, end = start[0], start[1]

    selected_categories = st.sidebar.multiselect(
        "Product type (category)",
        options=all_categories,
        default=all_categories,
        help="Momence category: Pack, Class, Product, Subscription, etc.",
    )

    filtered = filter_sales(raw, selected_categories, start, end)
    daily = daily_totals(filtered)

    if filtered.empty:
        st.warning("No rows match the current filters.")
        return

    total = filtered["net_sales"].sum()
    transactions = len(filtered)
    _metric_row(daily, total, transactions, start, end)

    _daily_chart(daily)
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
