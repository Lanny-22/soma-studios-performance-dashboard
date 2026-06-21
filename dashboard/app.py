"""Password-protected SOMA Studios analytics — multi-page Streamlit app."""

import streamlit as st

from dashboard.shared import (
    load_class_occupancy_or_error,
    load_expenses_or_error,
    load_financial_model_or_error,
    load_instructor_or_error,
    load_sales_or_error,
    password_gate,
    sidebar_date_range,
    sidebar_header,
)
from dashboard.views.budget_vs_actuals import render as render_budget_vs_actuals
from dashboard.views.budget_vs_actuals import render_model_budget
from dashboard.views.downloads import render as render_downloads
from dashboard.views.expenses import render as render_expenses
from dashboard.views.instructors import render as render_instructors
from dashboard.views.packages import render as render_packages
from dashboard.views.peak_times import render as render_peak_times
from dashboard.views.products import render as render_products
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


def _run_products() -> None:
    render_products(
        st.session_state["dash_raw"],
        st.session_state["dash_start"],
        st.session_state["dash_end"],
    )


def _run_instructors() -> None:
    raw = st.session_state.get("dash_instructor_raw")
    if raw is None or raw.empty:
        st.warning("No instructor performance data found.")
        return
    render_instructors(
        raw,
        st.session_state["dash_start"],
        st.session_state["dash_end"],
    )


def _run_peak_times() -> None:
    render_peak_times(
        st.session_state.get("dash_occupancy_raw"),
        st.session_state["dash_start"],
        st.session_state["dash_end"],
    )


def _run_expenses() -> None:
    raw = st.session_state.get("dash_expense_raw")
    if raw is None or raw.empty:
        st.warning("No expense data found.")
        return
    render_expenses(
        raw,
        st.session_state["dash_start"],
        st.session_state["dash_end"],
    )


def _run_budget_vs_actuals() -> None:
    budget = st.session_state.get("dash_budget_raw")
    if budget is None or budget.empty:
        st.warning("No financial model budget data found.")
        return
    render_budget_vs_actuals(
        st.session_state["dash_raw"],
        st.session_state.get("dash_instructor_raw"),
        budget,
        st.session_state.get("dash_expense_raw"),
    )


def _run_model_budget() -> None:
    budget = st.session_state.get("dash_budget_raw")
    if budget is None or budget.empty:
        st.warning("No financial model budget data found.")
        return
    render_model_budget(budget)


def _run_downloads() -> None:
    render_downloads(
        st.session_state.get("dash_raw"),
        st.session_state.get("dash_expense_raw"),
        st.session_state.get("dash_instructor_raw"),
        st.session_state.get("dash_occupancy_raw"),
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

    expenses = load_expenses_or_error()
    occupancy = load_class_occupancy_or_error()
    start, end = sidebar_date_range(raw, expenses=expenses, occupancy=occupancy)
    st.session_state["dash_raw"] = raw
    st.session_state["dash_start"] = start
    st.session_state["dash_end"] = end
    st.session_state["dash_instructor_raw"] = load_instructor_or_error()
    st.session_state["dash_expense_raw"] = expenses
    st.session_state["dash_occupancy_raw"] = occupancy
    st.session_state["dash_budget_raw"] = load_financial_model_or_error()

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
            st.Page(
                _run_products,
                title="Product Sales",
                icon="🛍️",
                url_path="product-sales",
            ),
            st.Page(
                _run_instructors,
                title="Instructor Performance",
                icon="🧘",
                url_path="instructor-performance",
            ),
            st.Page(
                _run_peak_times,
                title="Peak Times",
                icon="🕐",
                url_path="peak-times",
            ),
            st.Page(
                _run_expenses,
                title="Expense Tracking",
                icon="💳",
                url_path="expense-tracking",
            ),
            st.Page(
                _run_budget_vs_actuals,
                title="Budget vs Actuals",
                icon="📈",
                url_path="budget-vs-actuals",
            ),
            st.Page(
                _run_model_budget,
                title="Model Budget",
                icon="📋",
                url_path="model-budget",
            ),
            st.Page(
                _run_downloads,
                title="Downloads",
                icon="📥",
                url_path="downloads",
            ),
        ],
    )
    nav.run()


if __name__ == "__main__":
    main()
