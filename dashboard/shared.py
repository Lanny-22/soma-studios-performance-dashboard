"""Shared dashboard UI: auth, branding, filters, data loading."""

from __future__ import annotations

import hmac
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.data import (
    load_class_occupancy,
    load_instructor_performance,
    load_revolut_expenses,
    load_total_sales,
)
from src.config import get_settings

ROOT = Path(__file__).resolve().parents[1]

EUR = "€{:,.2f}"
BLACK = "#1b1b1b"
GREEN = "#2d6a4f"
GREEN_LIGHT = "#40916c"
CHART_HEIGHT = 620
BAR_CHART_HEIGHT = 480
PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True}
DAY_MS = 24 * 60 * 60 * 1000

LOGO_PATH = ROOT / "assets" / "SomaLogo.png"


def logo_source() -> str | None:
    if LOGO_PATH.is_file():
        return str(LOGO_PATH)
    url = os.environ.get("LOGO_URL", "").strip()
    if url:
        return url
    try:
        if hasattr(st, "secrets") and "LOGO_URL" in st.secrets:
            return str(st.secrets["LOGO_URL"]).strip()
    except Exception:
        pass
    return None


def show_logo(width: int = 180) -> None:
    if LOGO_PATH.is_file():
        st.image(LOGO_PATH.read_bytes(), width=width)
        return
    source = logo_source()
    if source:
        st.image(source, width=width)


def password_gate() -> bool:
    settings = get_settings()
    expected = settings.dashboard_password
    if not expected:
        st.error("Set DASHBOARD_PASSWORD in your .env file before opening the dashboard.")
        st.stop()

    if st.session_state.get("authenticated"):
        return True

    show_logo(200)
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


def sidebar_header() -> None:
    if st.sidebar.button("Sign out"):
        st.session_state.authenticated = False
        st.rerun()
    show_logo(150)
    st.sidebar.divider()


@st.cache_data(ttl=300, show_spinner="Loading instructor data from Supabase…")
def cached_instructor_performance() -> pd.DataFrame:
    return load_instructor_performance()


@st.cache_data(ttl=300, show_spinner="Loading sales from Supabase…")
def cached_sales() -> pd.DataFrame:
    return load_total_sales()


@st.cache_data(ttl=300, show_spinner="Loading class occupancy from Supabase…")
def cached_class_occupancy() -> pd.DataFrame:
    return load_class_occupancy()


@st.cache_data(ttl=300, show_spinner="Loading expense data from Supabase…")
def cached_expenses() -> pd.DataFrame:
    return load_revolut_expenses(include_excluded=False)


@st.cache_data(ttl=300, show_spinner="Loading all expense rows…")
def cached_all_expenses() -> pd.DataFrame:
    return load_revolut_expenses(include_excluded=True)


def clear_expense_cache() -> None:
    cached_expenses.clear()
    cached_all_expenses.clear()


def load_instructor_or_error() -> pd.DataFrame | None:
    try:
        return cached_instructor_performance()
    except Exception as exc:
        err = str(exc)
        st.error("Could not load instructor performance data.")
        with st.expander("Technical details"):
            st.code(err)
        return None


def load_class_occupancy_or_error() -> pd.DataFrame | None:
    try:
        return cached_class_occupancy()
    except Exception as exc:
        err = str(exc)
        st.error("Could not load class occupancy data.")
        with st.expander("Technical details"):
            st.code(err)
        return None


def load_sales_or_error() -> pd.DataFrame | None:
    try:
        return cached_sales()
    except Exception as exc:
        err = str(exc)
        st.error("Could not connect to Supabase.")
        if "authentication failures" in err or "CIRCUITBREAKER" in err:
            st.warning(
                "Supabase blocked connections after repeated **wrong database password** attempts. "
                "Stop the app (Reboot), wait 2 minutes, then fix **DATABASE_URL** in Streamlit secrets."
            )
        else:
            st.caption("Check DATABASE_URL in Streamlit secrets.")
        with st.expander("Technical details"):
            st.code(err)
        return None


def load_expenses_or_error() -> pd.DataFrame | None:
    try:
        return cached_expenses()
    except Exception as exc:
        err = str(exc)
        st.error("Could not load Revolut expense data.")
        with st.expander("Technical details"):
            st.code(err)
        return None


def date_bounds(raw: pd.DataFrame, date_col: str = "sale_date") -> tuple[date, date]:
    return raw[date_col].min(), raw[date_col].max()


def combined_date_bounds(
    sales: pd.DataFrame,
    expenses: pd.DataFrame | None = None,
    occupancy: pd.DataFrame | None = None,
) -> tuple[date, date]:
    min_date, max_date = date_bounds(sales)
    if expenses is not None and not expenses.empty:
        exp_min, exp_max = date_bounds(expenses, "expense_date")
        min_date = min(min_date, exp_min)
        max_date = max(max_date, exp_max)
    if occupancy is not None and not occupancy.empty:
        occ_min, occ_max = date_bounds(occupancy, "class_date")
        min_date = min(min_date, occ_min)
        max_date = max(max_date, occ_max)
    return min_date, max_date


def sidebar_date_range(
    raw: pd.DataFrame,
    header: str = "Filters",
    expenses: pd.DataFrame | None = None,
    occupancy: pd.DataFrame | None = None,
) -> tuple[date, date]:
    min_date, max_date = combined_date_bounds(raw, expenses, occupancy)
    st.sidebar.header(header)
    start, end = st.sidebar.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="global_date_range",
    )
    if not isinstance(start, date):
        start, end = start[0], start[1]
    return start, end


def filter_date_range(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return df[(df["sale_date"] >= start) & (df["sale_date"] <= end)]


def client_request_meta() -> dict[str, str | None]:
    """Best-effort client IP and user agent (Streamlit Cloud / reverse proxy)."""
    ip_address: str | None = None
    user_agent: str | None = None
    try:
        ctx = st.context
        if hasattr(ctx, "ip_address") and ctx.ip_address:
            ip_address = str(ctx.ip_address)
        headers = getattr(ctx, "headers", None) or {}
        if not ip_address and headers:
            forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
            if forwarded:
                ip_address = str(forwarded).split(",")[0].strip()
            if not ip_address:
                ip_address = headers.get("X-Real-Ip") or headers.get("x-real-ip")
        if headers:
            user_agent = headers.get("User-Agent") or headers.get("user-agent")
    except Exception:
        pass
    return {"ip_address": ip_address, "user_agent": user_agent}


def download_user_names() -> tuple[str | None, str | None]:
    first = (st.session_state.get("download_user_first_name") or "").strip()
    last = (st.session_state.get("download_user_last_name") or "").strip()
    return first or None, last or None
