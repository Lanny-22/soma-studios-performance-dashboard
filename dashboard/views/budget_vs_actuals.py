"""Budget vs actuals by financial-model period (13th–13th)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from dashboard.data import (
    BUDGET_REVENUE_CATEGORIES,
    FIXED_COST_CATEGORY_ORDER,
    TOTAL_FIXED_EXPENSES_LABEL,
    add_budget_model_cumulative,
    add_cumulative_columns,
    add_fixed_costs_budget_cumulative,
    add_fixed_costs_cumulative,
    attach_actual_net_profit,
    build_budget_model_variable,
    build_budget_vs_actuals,
    build_fixed_costs_budget_long,
    build_fixed_costs_comparison,
    enrich_budget_periods,
)
from dashboard.shared import CHART_HEIGHT, GREEN, GREEN_LIGHT, PLOTLY_CONFIG

MetricFmt = Callable[[float | None], str]
VarianceKind = Literal["revenue", "expense", "margin"]

FIXED_GRANULAR_KEY = "budget_fixed_granular"
MODEL_FIXED_GRANULAR_KEY = "budget_model_fixed_granular"

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


@dataclass(frozen=True)
class BudgetOnlySpec:
    label: str
    col: str
    fmt: MetricFmt


def _format_money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"€{int(round(float(value))):,}"


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

BUDGET_ONLY_VARIABLE_SPECS: list[BudgetOnlySpec] = [
    BudgetOnlySpec("Revenue", "budget_revenue", _format_money),
    BudgetOnlySpec("Instructor Fees", "budget_instructor_fees", _format_money),
    BudgetOnlySpec("Gross Margin", "budget_gross_margin_pct", _format_pct),
]

BUDGET_ONLY_CUM_VARIABLE_SPECS: list[BudgetOnlySpec] = [
    BudgetOnlySpec("Revenue", "cum_budget_revenue", _format_money),
    BudgetOnlySpec("Instructor Fees", "cum_budget_instructor_fees", _format_money),
    BudgetOnlySpec("Gross Margin", "cum_budget_gross_margin_pct", _format_pct),
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


def _build_budget_only_pivot(
    df: pd.DataFrame,
    specs: list[BudgetOnlySpec],
) -> pd.DataFrame:
    period_codes = df["period_code"].tolist()
    by_period = df.set_index("period_code")
    period_headers = [
        f"{code}\n{by_period.loc[code]['period_range']}" for code in period_codes
    ]

    rows: list[dict[str, str]] = []
    for spec in specs:
        cells: dict[str, str] = {"Metric": spec.label}
        for code, header in zip(period_codes, period_headers):
            cells[header] = spec.fmt(by_period.loc[code][spec.col])
        rows.append(cells)

    return pd.DataFrame(rows)


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


def _build_budget_only_from_long(
    long_df: pd.DataFrame,
    categories: list[str],
    *,
    cumulative: bool = False,
) -> pd.DataFrame:
    budget_col = "cum_budget_amount" if cumulative else "budget_amount"

    period_meta = long_df.sort_values("period_index").drop_duplicates("period_code")
    period_codes = period_meta["period_code"].tolist()
    period_headers = [
        f"{row.period_code}\n{row.period_range}" for row in period_meta.itertuples()
    ]
    indexed = long_df.set_index(["period_code", "category"])

    rows: list[dict[str, str]] = []
    for category in categories:
        cells: dict[str, str] = {"Metric": category}
        for code, header in zip(period_codes, period_headers):
            if (code, category) not in indexed.index:
                cells[header] = "—"
                continue
            cells[header] = _format_money(float(indexed.loc[(code, category)][budget_col]))
        rows.append(cells)

    return pd.DataFrame(rows)


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


def _style_budget_only(table: pd.DataFrame):
    def _row_style(_row: pd.Series) -> list[str]:
        styles = [""] * len(_row)
        styles[_row.index.get_loc("Metric")] = METRIC_BG
        return styles

    return table.style.apply(_row_style, axis=1)


def _show_pivot_table(df: pd.DataFrame, specs: list[MetricSpec]) -> None:
    table, meta = _build_pivot_rows(df, specs)
    st.dataframe(_style_pivot(table, meta), use_container_width=True, hide_index=True)


def _show_budget_only_table(df: pd.DataFrame, specs: list[BudgetOnlySpec]) -> None:
    table = _build_budget_only_pivot(df, specs)
    st.dataframe(_style_budget_only(table), use_container_width=True, hide_index=True)


def _show_pivot_from_long(
    long_df: pd.DataFrame,
    categories: list[str],
    *,
    cumulative: bool = False,
) -> None:
    table, meta = _build_pivot_from_long(long_df, categories, cumulative=cumulative)
    st.dataframe(_style_pivot(table, meta), use_container_width=True, hide_index=True)


def _show_budget_only_from_long(
    long_df: pd.DataFrame,
    categories: list[str],
    *,
    cumulative: bool = False,
) -> None:
    table = _build_budget_only_from_long(long_df, categories, cumulative=cumulative)
    st.dataframe(_style_budget_only(table), use_container_width=True, hide_index=True)


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
    granular_key: str = FIXED_GRANULAR_KEY,
) -> None:
    _section_header("Fixed Costs Overview")

    granular = st.session_state.get(granular_key, False)
    if st.button(
        "Show line-item detail" if not granular else "Show total only",
        key=f"fixed_granular_{granular_key}_{'cum' if cumulative else 'monthly'}",
    ):
        st.session_state[granular_key] = not granular
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


def _render_fixed_budget_only_section(
    fixed_long: pd.DataFrame,
    fixed_cumulative: pd.DataFrame,
    *,
    cumulative: bool = False,
) -> None:
    _section_header("Fixed Costs Overview")

    granular = st.session_state.get(MODEL_FIXED_GRANULAR_KEY, False)
    if st.button(
        "Show line-item detail" if not granular else "Show total only",
        key=f"model_fixed_granular_{'cum' if cumulative else 'monthly'}",
    ):
        st.session_state[MODEL_FIXED_GRANULAR_KEY] = not granular
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
    _show_budget_only_from_long(source, categories, cumulative=cumulative)
    st.caption("Budget from financial model (all planned periods).")


def _period_axis_labels(df: pd.DataFrame) -> list[str]:
    return [f"{row.period_code}" for row in df.itertuples()]


def _budget_actual_line_chart(
    df: pd.DataFrame,
    *,
    title: str,
    budget_col: str,
    actual_col: str,
    y_title: str,
    value_kind: Literal["eur", "pct"],
) -> None:
    if df.empty:
        return

    x = _period_axis_labels(df)
    budget = df[budget_col].astype(float)
    actual = df[actual_col].astype(float)

    if value_kind == "eur":
        budget_hover = budget.map(lambda v: f"€{int(round(v)):,}")
        actual_hover = actual.map(lambda v: f"€{int(round(v)):,}")
        tick_format = ",.0f"
    else:
        budget_hover = budget.map(lambda v: f"{v:.1f}%")
        actual_hover = actual.map(lambda v: f"{v:.1f}%")
        tick_format = ".1f"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=budget,
            mode="lines+markers",
            name="Budget",
            line=dict(color=GREEN_LIGHT, width=2.5, dash="dash"),
            marker=dict(size=7),
            hovertemplate="%{x}<br>Budget: %{customdata}<extra></extra>",
            customdata=budget_hover,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=actual,
            mode="lines+markers",
            name="Actual",
            line=dict(color=GREEN, width=3),
            marker=dict(size=8),
            hovertemplate="%{x}<br>Actual: %{customdata}<extra></extra>",
            customdata=actual_hover,
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Studio period",
        yaxis_title=y_title,
        height=CHART_HEIGHT,
        margin=dict(l=10, r=10, t=50, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_yaxes(tickformat=tick_format)
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def _render_cumulative_net_profit_charts(cumulative: pd.DataFrame) -> None:
    _section_header("Cumulative Net Profit & Margin")

    metric = st.radio(
        "Metric",
        ["Net profit", "Net margin"],
        horizontal=True,
        key="cumulative_net_metric",
    )

    if metric == "Net profit":
        _budget_actual_line_chart(
            cumulative,
            title="Cumulative net profit",
            budget_col="cum_budget_net_profit",
            actual_col="cum_actual_net_profit",
            y_title="Cumulative net profit (€)",
            value_kind="eur",
        )
    else:
        _budget_actual_line_chart(
            cumulative,
            title="Cumulative net margin",
            budget_col="cum_budget_net_margin_pct",
            actual_col="cum_actual_net_margin_pct",
            y_title="Cumulative net margin (%)",
            value_kind="pct",
        )

    st.caption(
        "Net profit = revenue − instructor fees − fixed operating expenses. "
        "Cumulative margin = cumulative net profit ÷ cumulative revenue."
    )


def _render_comparison_tab(
    started: pd.DataFrame,
    cumulative: pd.DataFrame,
    fixed_long: pd.DataFrame,
    fixed_cumulative: pd.DataFrame,
) -> None:
    var_monthly_tab, var_cumulative_tab = st.tabs(["Monthly by period", "Cumulative"])

    with var_monthly_tab:
        _render_variable_section(started)

    with var_cumulative_tab:
        _render_variable_section_cumulative(cumulative)

    st.divider()

    fixed_view = st.radio(
        "Fixed costs view",
        ["Monthly by period", "Cumulative"],
        horizontal=True,
        key="comparison_fixed_costs_view",
    )
    _render_fixed_section(
        fixed_long,
        fixed_cumulative,
        cumulative=fixed_view == "Cumulative",
    )


def render_model_budget(budget: pd.DataFrame) -> None:
    st.title("Model Budget")
    st.caption(
        "Full financial model budget across all planned studio periods "
        "(13th → 12th, from 13 May 2026)."
    )

    if budget.empty:
        st.warning("No financial model periods found. Run `python3 scripts/run_financial_model_import.py`.")
        return

    periods = enrich_budget_periods(budget)
    variable_df = build_budget_model_variable(budget)
    variable_cumulative = add_budget_model_cumulative(variable_df)
    fixed_long = build_fixed_costs_budget_long(periods)
    fixed_cumulative = add_fixed_costs_budget_cumulative(fixed_long)

    var_monthly_tab, var_cumulative_tab = st.tabs(["Monthly by period", "Cumulative"])

    with var_monthly_tab:
        _section_header("Revenue less Variable Costs Overview")
        _show_budget_only_table(variable_df, BUDGET_ONLY_VARIABLE_SPECS)
        st.caption("Budget from financial model.")

    with var_cumulative_tab:
        _section_header("Revenue less Variable Costs Overview")
        _show_budget_only_table(variable_cumulative, BUDGET_ONLY_CUM_VARIABLE_SPECS)
        st.caption("Running budget totals through each period end.")

    st.divider()

    fixed_view = st.radio(
        "Fixed costs view",
        ["Monthly by period", "Cumulative"],
        horizontal=True,
        key="model_fixed_costs_view",
    )
    _render_fixed_budget_only_section(
        fixed_long,
        fixed_cumulative,
        cumulative=fixed_view == "Cumulative",
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

    fixed_long = build_fixed_costs_comparison(expense_df, started)
    started = attach_actual_net_profit(started, fixed_long)
    cumulative = add_cumulative_columns(started)
    fixed_cumulative = add_fixed_costs_cumulative(fixed_long)

    current_mask = (started["period_start"] <= today) & (started["period_end"] >= today)
    if current_mask.any() and started.loc[current_mask, "period_end"].iloc[-1] >= today:
        focus = started[current_mask].iloc[-1]
        st.info(
            f"**{focus['period_label']}** is in progress ({focus['period_range']}). "
            "Actual figures for the current period are partial."
        )

    _render_comparison_tab(started, cumulative, fixed_long, fixed_cumulative)

    st.divider()

    _render_cumulative_net_profit_charts(cumulative)

    st.caption(
        "Revenue & margin: red if variance < −15%, orange −15% to −5%, green ≥ −5%. "
        "Variable & fixed expenses: green < 5% over budget, orange 5–15%, red > 15%."
    )
