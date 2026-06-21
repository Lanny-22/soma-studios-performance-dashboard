"""Budget vs actuals by financial-model period (13th–13th)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

import pandas as pd
import streamlit as st

from dashboard.data import (
    BUDGET_REVENUE_CATEGORIES,
    FIXED_COST_CATEGORY_ORDER,
    TOTAL_FIXED_EXPENSES_LABEL,
    add_cumulative_columns,
    add_fixed_costs_cumulative,
    build_budget_vs_actuals,
    build_fixed_costs_comparison,
)
from dashboard.shared import EUR

MetricFmt = Callable[[float | None], str]
VarianceKind = Literal["revenue", "expense", "margin"]

FIXED_GRANULAR_KEY = "budget_fixed_granular"

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


VARIABLE_METRIC_SPECS: list[MetricSpec] = [
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

VARIABLE_CUM_METRIC_SPECS: list[MetricSpec] = [
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


def _build_pivot_rows(
    df: pd.DataFrame,
    specs: list[MetricSpec],
) -> tuple[pd.DataFrame, list[PivotRow]]:
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


def _build_pivot_from_long(
    long_df: pd.DataFrame,
    categories: list[str],
    *,
    cumulative: bool = False,
) -> tuple[pd.DataFrame, list[PivotRow]]:
    budget_col = "cum_budget_amount" if cumulative else "budget_amount"
    actual_col = "cum_actual_amount" if cumulative else "actual_amount"

    period_meta = long_df.sort_values("period_index").drop_duplicates("period_code")
    period_codes = period_meta["period_code"].tolist()
    period_headers = [
        f"{row.period_code}\n{row.period_range}" for row in period_meta.itertuples()
    ]
    indexed = long_df.set_index(["period_code", "category"])

    pivot_rows: list[PivotRow] = []
    for category in categories:
        actual_cells: dict[str, str] = {"Metric": category, "": "Actual"}
        budget_cells: dict[str, str] = {"Metric": "", "": "Budget"}
        variance_cells: dict[str, str] = {"Metric": "", "": "Variance"}
        variance_values: dict[str, float | None] = {}

        for code, header in zip(period_codes, period_headers):
            if (code, category) not in indexed.index:
                actual_cells[header] = "—"
                budget_cells[header] = "—"
                variance_cells[header] = "—"
                continue

            row = indexed.loc[(code, category)]
            actual = float(row[actual_col])
            budget = float(row[budget_col])
            actual_cells[header] = _format_money(actual)
            budget_cells[header] = _format_money(budget)
            var_value = _variance_pct(actual, budget)
            variance_cells[header] = _format_variance_pct(var_value)
            variance_values[header] = var_value

        pivot_rows.extend(
            [
                PivotRow(actual_cells, category, "actual"),
                PivotRow(budget_cells, category, "budget"),
                PivotRow(
                    variance_cells,
                    category,
                    "variance",
                    "expense",
                    variance_values,
                ),
            ]
        )

    return pd.DataFrame([row.cells for row in pivot_rows]), pivot_rows


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


def _show_pivot_table(df: pd.DataFrame, specs: list[MetricSpec]) -> None:
    table, meta = _build_pivot_rows(df, specs)
    st.dataframe(_style_pivot(table, meta), use_container_width=True, hide_index=True)


def _show_pivot_from_long(
    long_df: pd.DataFrame,
    categories: list[str],
    *,
    cumulative: bool = False,
) -> None:
    table, meta = _build_pivot_from_long(long_df, categories, cumulative=cumulative)
    st.dataframe(_style_pivot(table, meta), use_container_width=True, hide_index=True)


def _section_header(title: str) -> None:
    st.markdown(f"**{title}**")


def _render_variable_section(started: pd.DataFrame) -> None:
    _section_header("Revenue less Variable Costs Overview")
    _show_pivot_table(started, VARIABLE_METRIC_SPECS)
    st.caption(
        "Revenue by payment date (Momence). Instructor fees by class date. "
        "Gross margin = (revenue − instructor payouts) ÷ revenue."
    )


def _render_variable_section_cumulative(cumulative: pd.DataFrame) -> None:
    _section_header("Revenue less Variable Costs Overview")
    _show_pivot_table(cumulative, VARIABLE_CUM_METRIC_SPECS)
    st.caption("Running totals through each period end.")


def _render_fixed_section(
    fixed_long: pd.DataFrame,
    fixed_cumulative: pd.DataFrame,
    *,
    cumulative: bool = False,
) -> None:
    _section_header("Fixed Costs Overview")

    granular = st.session_state.get(FIXED_GRANULAR_KEY, False)
    if st.button(
        "Show line-item detail" if not granular else "Show total only",
        key=f"fixed_granular_{'cum' if cumulative else 'monthly'}",
    ):
        st.session_state[FIXED_GRANULAR_KEY] = not granular
        st.rerun()

    if fixed_long.empty:
        st.warning("No fixed-cost budget data found.")
        return

    if granular:
        categories = [
            c for c in FIXED_COST_CATEGORY_ORDER if c in fixed_long["category"].unique()
        ]
    else:
        categories = [TOTAL_FIXED_EXPENSES_LABEL]

    source = fixed_cumulative if cumulative else fixed_long
    _show_pivot_from_long(source, categories, cumulative=cumulative)
    st.caption(
        "Budget from financial model. Actual from Revolut expenses by label "
        "(completed date, Malta). Expense variance: green < 5%, orange 5–15%, red > 15%."
    )


def render(
    sales: pd.DataFrame,
    instructors: pd.DataFrame | None,
    budget: pd.DataFrame,
    expenses: pd.DataFrame | None,
) -> None:
    st.title("Budget vs Actuals")
    st.caption(
        "Financial model vs actuals by **studio period** (13th → 12th, from 13 May 2026). "
        f"Revenue = {', '.join(BUDGET_REVENUE_CATEGORIES)} net sales."
    )

    if budget.empty:
        st.warning("No financial model periods found. Run `python3 scripts/run_financial_model_import.py`.")
        return

    instructor_df = instructors if instructors is not None else pd.DataFrame()
    expense_df = expenses if expenses is not None else pd.DataFrame()
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
    fixed_long = build_fixed_costs_comparison(expense_df, started)
    fixed_cumulative = add_fixed_costs_cumulative(fixed_long)

    current_mask = (started["period_start"] <= today) & (started["period_end"] >= today)
    if current_mask.any() and started.loc[current_mask, "period_end"].iloc[-1] >= today:
        focus = started[current_mask].iloc[-1]
        st.info(
            f"**{focus['period_label']}** is in progress ({focus['period_range']}). "
            "Actual figures for the current period are partial."
        )

    monthly_tab, cumulative_tab = st.tabs(["Monthly by period", "Cumulative"])

    with monthly_tab:
        _render_variable_section(started)
        st.divider()
        _render_fixed_section(fixed_long, fixed_cumulative, cumulative=False)

    with cumulative_tab:
        _render_variable_section_cumulative(cumulative)
        st.divider()
        _render_fixed_section(fixed_long, fixed_cumulative, cumulative=True)

    st.caption(
        "Revenue & margin: red if variance < −15%, orange −15% to −5%, green ≥ −5%. "
        "Variable & fixed expenses: green < 5% over budget, orange 5–15%, red > 15%."
    )
