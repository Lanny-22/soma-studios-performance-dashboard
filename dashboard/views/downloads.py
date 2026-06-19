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
    log_download_event,
)
from dashboard.shared import cached_all_expenses, cached_class_occupancy, client_request_meta, download_user_names


def _download_filename(prefix: str, start: date, end: date) -> str:
    return f"{prefix}_{start:%Y%m%d}_{end:%Y%m%d}.csv"


def _record_download(
    dataset_key: str,
    dataset_label: str,
    file_name: str,
    range_start: str,
    range_end: str,
    row_count: int,
) -> None:
    meta = client_request_meta()
    first_name, last_name = download_user_names()
    log_download_event(
        dataset_key=dataset_key,
        dataset_label=dataset_label,
        file_name=file_name,
        date_range_start=date.fromisoformat(range_start),
        date_range_end=date.fromisoformat(range_end),
        row_count=row_count,
        ip_address=meta.get("ip_address"),
        user_agent=meta.get("user_agent"),
        first_name=first_name,
        last_name=last_name,
    )


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
    occupancy: pd.DataFrame | None = None,
) -> None:
    st.title("Downloads")
    st.caption("Export CSV files for the date range and datasets you choose.")

    sales_export = _cached_sales_export()
    expenses_all = cached_all_expenses()
    instructors_export = instructors if instructors is not None else _cached_instructors_export()
    occupancy_export = occupancy if occupancy is not None else cached_class_occupancy()

    min_date, max_date = combined_download_date_bounds(
        sales_export,
        expenses_all,
        instructors_export,
        occupancy_export,
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

    with st.expander("Your details (optional)", expanded=False):
        st.caption("If provided, your name is stored in the download audit log with each export.")
        n1, n2 = st.columns(2)
        n1.text_input("First name", key="download_user_first_name")
        n2.text_input("Last name", key="download_user_last_name")

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
            occupancy=occupancy_export,
        )

        st.markdown(f"**{meta['label']}**")
        st.caption(meta["description"])

        if export_df.empty:
            st.warning("No rows in this date range.")
            continue

        st.caption(f"{len(export_df):,} rows")
        with st.expander("Preview (first 20 rows)", expanded=False):
            st.dataframe(export_df.head(20), use_container_width=True, hide_index=True)

        file_name = _download_filename(meta["file_prefix"], start, end)
        csv_bytes = export_df.to_csv(index=False).encode("utf-8")
        clicked = st.download_button(
            label=f"Download {meta['label']} CSV",
            data=csv_bytes,
            file_name=file_name,
            mime="text/csv",
            key=f"download_btn_{dataset_key}",
        )
        if clicked:
            try:
                _record_download(
                    dataset_key=dataset_key,
                    dataset_label=meta["label"],
                    file_name=file_name,
                    range_start=start.isoformat(),
                    range_end=end.isoformat(),
                    row_count=len(export_df),
                )
            except Exception as exc:
                st.error(f"Download started but logging failed: {exc}")
