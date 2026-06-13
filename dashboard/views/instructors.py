"""Instructor popularity and studio profitability rankings."""

from datetime import date

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import aggregate_instructors, filter_instructor_performance, instructor_month_comparison
from dashboard.shared import BAR_CHART_HEIGHT, BLACK, EUR, GREEN, GREEN_LIGHT, PLOTLY_CONFIG


def _horizontal_bars(
    df: pd.DataFrame,
    title: str,
    value_col: str,
    value_label: str,
    color: str,
) -> None:
    if df.empty:
        st.info("No instructor data for the selected date range.")
        return

    plot_df = df.sort_values(value_col, ascending=True)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=plot_df[value_col],
            y=plot_df["instructor_name"],
            orientation="h",
            marker_color=color,
            text=plot_df[value_col].map(
                lambda v: f"{v:,.0f}"
                if value_col in ("total_bookings", "class_count")
                else EUR.format(v)
            ),
            textposition="outside",
            cliponaxis=False,
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=value_label,
        yaxis_title="",
        height=BAR_CHART_HEIGHT,
        margin=dict(l=10, r=40, t=50, b=40),
        showlegend=False,
    )
    fig.update_yaxes(categoryorder="array", categoryarray=plot_df["instructor_name"].tolist())
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def render(raw: pd.DataFrame, start: date, end: date) -> None:
    st.title("Instructor Performance")
    st.caption(
        "Rankings from Momence instructor reports. "
        "Popularity uses total bookings; profitability is gross revenue minus instructor payout "
        "(studio net); net revenue per class is studio net divided by classes taught."
    )

    filtered = filter_instructor_performance(raw, start, end)
    if filtered.empty:
        st.warning("No instructor performance data overlaps the selected date range.")
        return

    ranked = aggregate_instructors(filtered)

    total_bookings = int(ranked["total_bookings"].sum())
    gross = ranked["gross_revenue"].sum()
    payouts = ranked["instructor_payout"].sum()
    studio_net = ranked["studio_net"].sum()
    total_classes = int(ranked["class_count"].sum())
    net_revenue_per_class = (studio_net / total_classes) if total_classes > 0 else 0
    margin = (studio_net / gross * 100) if gross > 0 else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total bookings", f"{total_bookings:,}")
    c2.metric("Classes taught", f"{total_classes:,}")
    c3.metric("Gross revenue", EUR.format(gross))
    c4.metric("Net revenue per class", EUR.format(net_revenue_per_class))
    c5.metric("Instructor payouts", EUR.format(payouts))
    c6.metric("Studio net", EUR.format(studio_net), f"{margin:.0f}% margin")

    by_popularity = ranked.sort_values("total_bookings", ascending=False)
    by_profit = ranked.sort_values("studio_net", ascending=False)
    by_net_revenue_per_class = ranked[ranked["class_count"] > 0].sort_values(
        "net_revenue_per_class", ascending=False
    )

    st.subheader("Rankings")
    tab_pop, tab_profit, tab_rpc = st.tabs(
        [
            "By popularity (bookings)",
            "By profitability (studio net)",
            "By net revenue per class",
        ]
    )

    with tab_pop:
        st.markdown("**Top instructors by total bookings** in the selected period.")
        _horizontal_bars(
            by_popularity.head(12),
            "Bookings by instructor",
            "total_bookings",
            "Total bookings",
            GREEN,
        )

    with tab_profit:
        st.markdown(
            "**Top instructors by studio net** (gross revenue − instructor payout) in the selected period."
        )
        _horizontal_bars(
            by_profit.head(12),
            "Studio net by instructor",
            "studio_net",
            "Studio net (€)",
            BLACK,
        )

    with tab_rpc:
        st.markdown(
            "**Top instructors by net revenue per class** (studio net ÷ classes taught)."
        )
        _horizontal_bars(
            by_net_revenue_per_class.head(12),
            "Net revenue per class by instructor",
            "net_revenue_per_class",
            "Net revenue per class (€)",
            GREEN_LIGHT,
        )

    st.subheader("Month-over-month")
    month_table = instructor_month_comparison(raw, start, end)
    if month_table.empty:
        st.info("No monthly instructor reports overlap the selected date range.")
    else:
        display_month = month_table.copy()
        for col in display_month.columns:
            if col.startswith("net_per_class_") or col == "net_per_class_change":
                display_month[col] = display_month[col].map(
                    lambda v: EUR.format(v) if pd.notna(v) else "—"
                )
            elif col.startswith("studio_net_"):
                display_month[col] = display_month[col].map(
                    lambda v: EUR.format(v) if pd.notna(v) else "—"
                )
            elif col.startswith("attendance_"):
                display_month[col] = display_month[col].map(
                    lambda v: f"{v:.1f}" if pd.notna(v) else "—"
                )
            elif col.startswith("classes_") or col == "classes_change":
                display_month[col] = display_month[col].map(
                    lambda v: f"{int(v)}" if pd.notna(v) else "—"
                )

        st.dataframe(display_month, use_container_width=True, hide_index=True)
        st.caption(
            "Monthly columns come from Momence instructor exports (full calendar months). "
            "Change columns compare the first and last month in your selected range."
        )

    st.subheader("Full instructor table")
    display = ranked.sort_values("total_bookings", ascending=False).copy()
    display["gross_revenue"] = display["gross_revenue"].map(lambda v: EUR.format(v))
    display["instructor_payout"] = display["instructor_payout"].map(lambda v: EUR.format(v))
    display["studio_net"] = display["studio_net"].map(lambda v: EUR.format(v))
    display["margin_pct"] = display["margin_pct"].map(lambda v: f"{v:.1f}%")
    display["net_revenue_per_class"] = display["net_revenue_per_class"].map(lambda v: EUR.format(v))
    display["average_attendance"] = display["average_attendance"].map(lambda v: f"{v:.1f}")
    display["total_hours"] = display["total_hours"].map(lambda v: f"{v:.1f}")

    display_cols = [
        "instructor_name",
        "total_bookings",
        "class_count",
        "average_attendance",
        "total_hours",
        "gross_revenue",
        "net_revenue_per_class",
        "instructor_payout",
        "studio_net",
        "margin_pct",
    ]
    st.dataframe(
        display[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "instructor_name": "Instructor",
            "total_bookings": st.column_config.NumberColumn("Bookings", format="%d"),
            "class_count": st.column_config.NumberColumn("Classes", format="%d"),
            "average_attendance": "Avg attendance",
            "total_hours": "Hours",
            "gross_revenue": "Gross revenue",
            "net_revenue_per_class": "Net revenue / class",
            "instructor_payout": "Instructor payout",
            "studio_net": "Studio net",
            "margin_pct": "Margin",
        },
    )
