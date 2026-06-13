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

    pages = [
        st.Page(
            lambda: render_total_sales(raw, start, end),
            title="Total Sales",
            icon="📊",
            default=True,
        ),
        st.Page(
            lambda: render_packages(raw, start, end),
            title="Packages & Subscriptions",
            icon="📦",
        ),
    ]

    nav = st.navigation(pages)
    nav.run()


if __name__ == "__main__":
    main()
