"""Shared dashboard UI: auth, branding, filters, data loading."""

from __future__ import annotations

import hmac
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.data import load_total_sales
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

LOGO_CANDIDATES = [
    ROOT / "assets" / "SomaLogo.png",
    ROOT / "assets" / "soma_logo.png",
    ROOT / "assets" / "logo.png",
]


def logo_source() -> str | None:
    for path in LOGO_CANDIDATES:
        if path.is_file():
            return str(path)
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


@st.cache_data(ttl=300, show_spinner="Loading sales from Supabase…")
def cached_sales() -> pd.DataFrame:
    return load_total_sales()


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


def date_bounds(raw: pd.DataFrame) -> tuple[date, date]:
    return raw["sale_date"].min(), raw["sale_date"].max()


def sidebar_date_range(raw: pd.DataFrame, header: str = "Filters") -> tuple[date, date]:
    min_date, max_date = date_bounds(raw)
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
