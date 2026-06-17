"""Export underlying sales and expense data as CSV."""

from datetime import date

import pandas as pd
import streamlit as st

from dashboard.data import (
    DOWNLOAD_DATASETS,
    build_download_export,
    combined_download_date_bounds,
    load_instructor_performance,
    load_total_sales_export,
)
from dashboard.shared import cached_all_expenses


def _download_filename(prefix: str, start: date, end: date) -> str:
    return f"{prefix}_{start:%Y%m%d}_{end:%Y%m%d}.csv"


@st.cache_data(ttl=300, show_spinner="Loading sales export data…")
def _cached_sales_export() -> pd.DataFrame:
    return load_total_sales_export()


@st.cache_data(ttl=300, show_spinner="Loading instructor export data…")
def _cached_instructors_export() -> pd.DataFrame:
    return load_instructor_performance()


def render(
    sales: pd.DataFrame | None,
    expenses: pd.DataFrame | None,
    instructors: pd.DataFrame | None,
) -> None:
    st.title("Downloads")
    st.caption("Export CSV files for the date range and datasets you choose.")

    sales_export = _cached_sales_export()
    expenses_all = cached_all_expenses()
    instructors_export = instructors if instructors is not None else _cached_instructors_export()

    min_date, max_date = combined_download_date_bounds(
        sales_export,
        expenses_all,
        instructors_export,
    )

    st.subheader("Export settings")
    c1, c2 = st.columns(2)
    with c1:
        start, end = st.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="download_date_range",
        )
    with c2:
        selected = st.multiselect(
            "Data to export",
            options=list(DOWNLOAD_DATASETS.keys()),
            default=["total_sales", "expenses"],
            format_func=lambda key: DOWNLOAD_DATASETS[key]["label"],
            key="download_dataset_filter",
        )

    if not isinstance(start, date):
        start, end = start[0], start[1]

    if not selected:
        st.info("Choose at least one dataset to export.")
        return

    st.divider()

    for dataset_key in selected:
        meta = DOWNLOAD_DATASETS[dataset_key]
        export_df = build_download_export(
            dataset_key,
            start,
            end,
            sales_export=sales_export,
            expenses_all=expenses_all,
            instructors=instructors_export,
        )

        st.markdown(f"**{meta['label']}**")
        st.caption(meta["description"])

        if export_df.empty:
            st.warning("No rows in this date range.")
            continue

        st.caption(f"{len(export_df):,} rows")
        with st.expander("Preview (first 20 rows)", expanded=False):
            st.dataframe(export_df.head(20), use_container_width=True, hide_index=True)

        csv_bytes = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"Download {meta['label']} CSV",
            data=csv_bytes,
            file_name=_download_filename(meta["file_prefix"], start, end),
            mime="text/csv",
            key=f"download_btn_{dataset_key}",
        )
