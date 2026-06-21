"""Budget vs actuals by financial-model period (13th–13th)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

import pandas as pd
import streamlit as st

from dashboard.data import (
    BUDGET_REVENUE_CATEGORIES,
    add_cumulative_columns,
    build_budget_vs_actuals,
)
from dashboard.shared import EUR

MetricFmt = Callable[[float | None], str]
VarianceKind = Literal["revenue", "expense", "margin"]

GREEN_BG = "background-color: #dcfce7"
ORANGE_BG = "background-color: #ffedd5"
RED_BG = "background-color: #fee2e2"
METRIC_BG = "background-color: #f3f4f6; font-weight: 600"
VARIANCE_ROW_STYLE = (
    "font-weight: 700; "
    "border-top: 2px solid #6b7280; "
    "border-bottom: 2px solid #6b7280"
)


def _join_styles(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


@dataclass(frozen=True)
class MetricSpec:
    label: str
    actual_col: str
    budget_col: str
    fmt: MetricFmt
    variance_kind: VarianceKind
    use_margin_points: bool = False


def _format_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    amount = float(value)
    if abs(amount) >= 1000:
        thousands = amount / 1000
        if abs(thousands - round(thousands)) < 0.05:
            return f"€{int(round(thousands)):,}k".replace(",", "")
        return EUR.format(amount)
    return EUR.format(amount)


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.0f}%"


def _variance_pct(actual: float, budget: float) -> float | None:
    if budget == 0 or pd.isna(budget) or pd.isna(actual):
        return None
    return (float(actual) - float(budget)) / float(budget) * 100


def _format_variance_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:+.0f}%"


def _format_variance_pp(actual: float, budget: float) -> tuple[str, float | None]:
    if pd.isna(actual) or pd.isna(budget):
        return "—", None
    points = float(actual) - float(budget)
    return f"{points:+.0f}pp", points


def _variance_color(value: float | None, kind: VarianceKind) -> str:
    if value is None or pd.isna(value):
        return ""

    if kind == "expense":
        if value < 5:
            return GREEN_BG
        if value <= 15:
            return ORANGE_BG
        return RED_BG

    if value < -15:
        return RED_BG
    if value < -5:
        return ORANGE_BG
    return GREEN_BG


METRIC_SPECS: list[MetricSpec] = [
    MetricSpec("Revenue", "actual_revenue", "budget_revenue", _format_money, "revenue"),
    MetricSpec(
        "Instructor Fees",
        "actual_instructor_fees",
        "budget_instructor_fees",
        _format_money,
        "expense",
    ),
    MetricSpec(
        "Gross Margin",
        "actual_gross_margin_pct",
        "budget_gross_margin_pct",
        _format_pct,
        "margin",
        use_margin_points=True,
    ),
]

CUM_METRIC_SPECS: list[MetricSpec] = [
    MetricSpec("Revenue", "cum_actual_revenue", "cum_budget_revenue", _format_money, "revenue"),
    MetricSpec(
        "Instructor Fees",
        "cum_actual_instructor_fees",
        "cum_budget_instructor_fees",
        _format_money,
        "expense",
    ),
    MetricSpec(
        "Gross Margin",
        "cum_actual_gross_margin_pct",
        "cum_budget_gross_margin_pct",
        _format_pct,
        "margin",
        use_margin_points=True,
    ),
]


@dataclass
class PivotRow:
    cells: dict[str, str]
    metric_label: str
    row_type: Literal["actual", "budget", "variance"]
    variance_kind: VarianceKind | None = None
    variance_values: dict[str, float | None] | None = None


def _build_pivot_rows(df: pd.DataFrame, specs: list[MetricSpec]) -> tuple[pd.DataFrame, list[PivotRow]]:
    period_codes = df["period_code"].tolist()
    by_period = df.set_index("period_code")
    period_headers = [
        f"{code}\n{by_period.loc[code]['period_range']}" for code in period_codes
    ]

    pivot_rows: list[PivotRow] = []
    for spec in specs:
        actual_cells: dict[str, str] = {"Metric": spec.label, "": "Actual"}
        budget_cells: dict[str, str] = {"Metric": "", "": "Budget"}
        variance_cells: dict[str, str] = {"Metric": "", "": "Variance"}
        variance_values: dict[str, float | None] = {}

        for code, header in zip(period_codes, period_headers):
            period = by_period.loc[code]
            actual = period[spec.actual_col]
            budget = period[spec.budget_col]
            actual_cells[header] = spec.fmt(actual)
            budget_cells[header] = spec.fmt(budget)

            if spec.use_margin_points:
                text, var_value = _format_variance_pp(actual, budget)
                variance_cells[header] = text
                variance_values[header] = var_value
            else:
                var_value = _variance_pct(actual, budget)
                variance_cells[header] = _format_variance_pct(var_value)
                variance_values[header] = var_value

        pivot_rows.extend(
            [
                PivotRow(actual_cells, spec.label, "actual"),
                PivotRow(budget_cells, spec.label, "budget"),
                PivotRow(
                    variance_cells,
                    spec.label,
                    "variance",
                    spec.variance_kind,
                    variance_values,
                ),
            ]
        )

    table = pd.DataFrame([row.cells for row in pivot_rows])
    return table, pivot_rows


def _style_pivot(table: pd.DataFrame, pivot_rows: list[PivotRow]):
    period_cols = [col for col in table.columns if col not in ("Metric", "")]

    def _row_style(row: pd.Series) -> list[str]:
        meta = pivot_rows[row.name]
        styles = [""] * len(row)
        if meta.row_type == "actual" and meta.metric_label:
            styles[row.index.get_loc("Metric")] = METRIC_BG
        if meta.row_type == "variance":
            for idx in range(len(row)):
                cell_style = VARIANCE_ROW_STYLE
                col = row.index[idx]
                if col in period_cols and meta.variance_values:
                    cell_style = _join_styles(
                        cell_style,
                        _variance_color(
                            meta.variance_values.get(col),
                            meta.variance_kind or "revenue",
                        ),
                    )
                styles[idx] = cell_style
        return styles

    return table.style.apply(_row_style, axis=1)


def render(
    sales: pd.DataFrame,
    instructors: pd.DataFrame | None,
    budget: pd.DataFrame,
) -> None:
    st.title("Budget vs Actuals")
    st.caption(
        "Financial model vs Momence actuals by **studio period** (13th → 12th, from 13 May 2026). "
        f"Revenue = {', '.join(BUDGET_REVENUE_CATEGORIES)} net sales by payment date. "
        "Instructor fees = Momence class payouts by class date. "
        "**Variance** = % vs budget (margin = percentage points). "
        "Green / orange / red thresholds differ for revenue vs expenses."
    )

    if budget.empty:
        st.warning("No financial model periods found. Run `python3 scripts/run_financial_model_import.py`.")
        return

    instructor_df = instructors if instructors is not None else pd.DataFrame()
    comparison = build_budget_vs_actuals(sales, instructor_df, budget)
    if comparison.empty:
        st.warning("Could not build budget comparison.")
        return

    today = date.today()
    started = comparison[comparison["period_start"] <= today].copy()
    if started.empty:
        st.info("No studio periods have started yet.")
        return

    cumulative = add_cumulative_columns(started)

    current_mask = (started["period_start"] <= today) & (started["period_end"] >= today)
    if current_mask.any() and started.loc[current_mask, "period_end"].iloc[-1] >= today:
        focus = started[current_mask].iloc[-1]
        st.info(
            f"**{focus['period_label']}** is in progress ({focus['period_range']}). "
            "Actual figures for that period are partial."
        )

    monthly_tab, cumulative_tab = st.tabs(["Monthly by period", "Cumulative"])

    with monthly_tab:
        monthly, monthly_meta = _build_pivot_rows(started, METRIC_SPECS)
        st.dataframe(
            _style_pivot(monthly, monthly_meta),
            use_container_width=True,
            hide_index=True,
        )

    with cumulative_tab:
        st.caption(
            "Running totals through each period end. "
            "Gross margin = cumulative gross profit ÷ cumulative revenue."
        )
        cumulative_table, cumulative_meta = _build_pivot_rows(cumulative, CUM_METRIC_SPECS)
        st.dataframe(
            _style_pivot(cumulative_table, cumulative_meta),
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "Revenue & margin: red if variance < −15%, orange −15% to −5%, green ≥ −5%. "
        "Instructor fees: green < 5% over budget, orange 5–15%, red > 15%."
    )
