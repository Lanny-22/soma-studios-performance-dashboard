"""Password-protected SOMA Studios analytics — multi-page Streamlit app."""

import streamlit as st

from dashboard.shared import (
    load_sales_or_error,
    password_gate,
    sidebar_date_range,
    sidebar_header,
)
from dashboard.views.packages import render as render_packages
from dashboard.views.total_sales import render as render_total_sales


def _run_total_sales() -> None:
    render_total_sales(
        st.session_state["dash_raw"],
        st.session_state["dash_start"],
        st.session_state["dash_end"],
    )


def _run_packages() -> None:
    render_packages(
        st.session_state["dash_raw"],
        st.session_state["dash_start"],
        st.session_state["dash_end"],
    )


def main() -> None:
    st.set_page_config(
        page_title="SOMA Studios — Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    if not password_gate():
        return

    sidebar_header()

    raw = load_sales_or_error()
    if raw is None or raw.empty:
        if raw is not None:
            st.warning("No sales data found in momence_total_sales.")
        return

    start, end = sidebar_date_range(raw)
    st.session_state["dash_raw"] = raw
    st.session_state["dash_start"] = start
    st.session_state["dash_end"] = end

    nav = st.navigation(
        [
            st.Page(
                _run_total_sales,
                title="Total Sales",
                icon="📊",
                default=True,
                url_path="total-sales",
            ),
            st.Page(
                _run_packages,
                title="Packages & Subscriptions",
                icon="📦",
                url_path="packages-subscriptions",
            ),
        ],
    )
    nav.run()


if __name__ == "__main__":
    main()
