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
    sum_pre_opening_expenses,
    sum_pre_opening_revenue,
)
from dashboard.shared import CHART_HEIGHT, GREEN, GREEN_LIGHT, PLOTLY_CONFIG, active_page_url_path

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


def _pre_opening_note(sales: pd.DataFrame, expenses: pd.DataFrame) -> str:
    presale_revenue = sum_pre_opening_revenue(sales)
    pre_opening_expenses = sum_pre_opening_expenses(expenses)
    return (
        "Budget vs actuals on this page exclude **presale revenue** and **pre-opening expenses** "
        "incurred to complete works on the premises (before 10 May 2026). "
        f"Presale revenue excluded: **{_format_money(presale_revenue)}**. "
        f"Pre-opening expenses excluded: **{_format_money(pre_opening_expenses)}**."
    )


def _render_net_profit_charts(
    started: pd.DataFrame,
    cumulative: pd.DataFrame,
    sales: pd.DataFrame,
    expenses: pd.DataFrame,
) -> None:
    _section_header("Net Profit & Margin")

    view = st.radio(
        "View",
        ["Cumulative", "Marginal"],
        horizontal=True,
        key="net_profit_view",
    )
    metric = st.radio(
        "Metric",
        ["Net profit", "Net margin"],
        horizontal=True,
        key="net_profit_metric",
    )

    is_cumulative = view == "Cumulative"
    source = cumulative if is_cumulative else started

    if metric == "Net profit":
        _budget_actual_line_chart(
            source,
            title="Cumulative net profit" if is_cumulative else "Net profit by period",
            budget_col="cum_budget_net_profit" if is_cumulative else "budget_net_profit",
            actual_col="cum_actual_net_profit" if is_cumulative else "actual_net_profit",
            y_title="Cumulative net profit (€)" if is_cumulative else "Net profit (€)",
            value_kind="eur",
        )
    else:
        _budget_actual_line_chart(
            source,
            title="Cumulative net margin" if is_cumulative else "Net margin by period",
            budget_col="cum_budget_net_margin_pct" if is_cumulative else "budget_net_margin_pct",
            actual_col="cum_actual_net_margin_pct" if is_cumulative else "actual_net_margin_pct",
            y_title="Cumulative net margin (%)" if is_cumulative else "Net margin (%)",
            value_kind="pct",
        )

    if is_cumulative:
        st.caption(
            "Net profit = gross profit − fixed operating expenses (EBITDA). "
            "Cumulative margin = cumulative net profit ÷ cumulative revenue."
        )
    else:
        st.caption(
            "Net profit = gross profit − fixed operating expenses (EBITDA). "
            "Marginal margin = period net profit ÷ period revenue."
        )

    st.caption(_pre_opening_note(sales, expenses))


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


def _period_select_label(comparison: pd.DataFrame, period_code: str) -> str:
    row = comparison.loc[comparison["period_code"] == period_code].iloc[0]
    return f"{period_code} ({row['period_range']})"


DEFAULT_PERIOD_CODE = "MAY26"
BUDGET_PERIOD_VALID_KEY = "budget_period_selection_valid"
BUDGET_TAB_ACTIVE_KEY = "budget_vs_actuals_tab_active"


def _default_period_code(comparison: pd.DataFrame, today: date) -> str:
    if DEFAULT_PERIOD_CODE in comparison["period_code"].values:
        return DEFAULT_PERIOD_CODE
    return str(comparison.sort_values("period_index").iloc[0]["period_code"])


def _reset_period_on_tab_access(period_codes: list[str], default_code: str) -> None:
    on_budget_tab = active_page_url_path() == "budget-vs-actuals"
    was_on_budget_tab = st.session_state.get(BUDGET_TAB_ACTIVE_KEY, False)
    st.session_state[BUDGET_TAB_ACTIVE_KEY] = on_budget_tab
    if on_budget_tab and not was_on_budget_tab:
        _set_period_checkboxes(period_codes, [default_code])
        st.session_state[BUDGET_PERIOD_VALID_KEY] = [default_code]


def _period_checkbox_key(period_code: str) -> str:
    return f"budget_period_cb_{period_code}"


def _set_period_checkboxes(period_codes: list[str], selected_codes: list[str]) -> None:
    selected = set(selected_codes)
    for code in period_codes:
        st.session_state[_period_checkbox_key(code)] = code in selected


def _selected_period_indices(period_codes: list[str]) -> list[int]:
    return [
        i
        for i, code in enumerate(period_codes)
        if st.session_state.get(_period_checkbox_key(code), False)
    ]


def _apply_period_toggle(
    period_codes: list[str],
    period_code: str,
) -> None:
    """Expand selection to fill gaps when checking; shrink from an edge when unchecking."""
    idx = period_codes.index(period_code)
    cb_key = _period_checkbox_key(period_code)
    checked = st.session_state[cb_key]
    selected = _selected_period_indices(period_codes)

    if checked:
        if not selected:
            return
        lo, hi = min(selected), max(selected)
        for i in range(min(lo, idx), max(hi, idx) + 1):
            st.session_state[_period_checkbox_key(period_codes[i])] = True
        return

    if len(selected) <= 1:
        st.session_state[cb_key] = True
        return

    lo, hi = min(selected), max(selected)
    if idx == lo:
        for i in range(lo, hi + 1):
            st.session_state[_period_checkbox_key(period_codes[i])] = i != lo
    elif idx == hi:
        for i in range(lo, hi + 1):
            st.session_state[_period_checkbox_key(period_codes[i])] = i != hi
    else:
        for i in range(lo, hi + 1):
            st.session_state[_period_checkbox_key(period_codes[i])] = i < idx


def _sidebar_period_selection(
    comparison: pd.DataFrame,
    today: date,
) -> tuple[list[str], int, int]:
    """Studio-period checkboxes; non-adjacent picks auto-fill the range in between."""
    period_codes = comparison.sort_values("period_index")["period_code"].tolist()
    default_code = _default_period_code(comparison, today)
    default_index = period_codes.index(default_code)

    _reset_period_on_tab_access(period_codes, default_code)

    if BUDGET_PERIOD_VALID_KEY not in st.session_state:
        st.session_state[BUDGET_PERIOD_VALID_KEY] = [default_code]

    for code in period_codes:
        cb_key = _period_checkbox_key(code)
        if cb_key not in st.session_state:
            st.session_state[cb_key] = code in st.session_state[BUDGET_PERIOD_VALID_KEY]

    st.sidebar.header("Filters")
    st.sidebar.caption(
        "Tick any period — all studio months in between are selected automatically."
    )
    st.sidebar.markdown("**Studio periods**")

    with st.sidebar.container(border=True):
        for code in period_codes:
            row = comparison.loc[comparison["period_code"] == code].iloc[0]

            def _on_toggle(*, _code: str = code) -> None:
                _apply_period_toggle(period_codes, _code)

            st.checkbox(
                code,
                key=_period_checkbox_key(code),
                help=str(row["period_range"]),
                on_change=_on_toggle,
            )

    selected_indices = _selected_period_indices(period_codes)
    if not selected_indices:
        selected_indices = [default_index]
        _set_period_checkboxes(period_codes, [default_code])

    selected_codes = [period_codes[i] for i in sorted(selected_indices)]
    st.session_state[BUDGET_PERIOD_VALID_KEY] = selected_codes

    min_period_index = int(
        comparison.loc[comparison["period_code"] == selected_codes[0], "period_index"].iloc[0]
    )
    max_period_index = int(
        comparison.loc[comparison["period_code"] == selected_codes[-1], "period_index"].iloc[0]
    )
    return selected_codes, min_period_index, max_period_index


def render(
    sales: pd.DataFrame,
    instructors: pd.DataFrame | None,
    budget: pd.DataFrame,
    expenses: pd.DataFrame | None,
) -> None:
    st.title("Budget vs Actuals")
    st.caption(
        "Financial model vs actuals by **studio period** (13th → 12th, from 13 May 2026). "
        f"Revenue = {', '.join(BUDGET_REVENUE_CATEGORIES)} net sales. "
        "Excludes presale revenue and pre-opening premises costs before 10 May 2026 "
        "(see totals at the bottom of the page)."
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
    selected_codes, min_period_index, max_period_index = _sidebar_period_selection(
        comparison, today
    )

    if len(selected_codes) == 1:
        selected = comparison[comparison["period_code"] == selected_codes[0]].iloc[0]
        st.caption(
            f"Actuals for **{selected['period_range']}** compared to **{selected_codes[0]}** budget."
        )
        if selected["period_start"] > today:
            st.info(f"**{selected_codes[0]}** has not started yet — actual figures will be zero.")
        elif selected["period_start"] <= today <= selected["period_end"]:
            st.info(
                f"**{selected_codes[0]}** is in progress ({selected['period_range']}). "
                "Actual figures for the current period are partial."
            )
    else:
        first = comparison[comparison["period_code"] == selected_codes[0]].iloc[0]
        last = comparison[comparison["period_code"] == selected_codes[-1]].iloc[0]
        st.caption(
            f"Actuals for **{selected_codes[0]}** through **{selected_codes[-1]}** "
            f"({first['period_start']:%d %b %Y} – {last['period_end']:%d %b %Y}) compared to budget."
        )
        in_progress = comparison[
            (comparison["period_code"].isin(selected_codes))
            & (comparison["period_start"] <= today)
            & (comparison["period_end"] >= today)
        ]
        if not in_progress.empty:
            focus = in_progress.iloc[-1]
            st.info(
                f"**{focus['period_code']}** is in progress ({focus['period_range']}). "
                "Actual figures for the current period are partial."
            )

    marginal = comparison[
        (comparison["period_index"] >= min_period_index)
        & (comparison["period_index"] <= max_period_index)
    ].copy()
    through = comparison[comparison["period_index"] <= max_period_index].copy()
    through_actual = through[through["period_start"] <= today].copy()

    fixed_long_marginal = build_fixed_costs_comparison(expense_df, marginal)
    marginal = attach_actual_net_profit(marginal, fixed_long_marginal)

    if through_actual.empty:
        cumulative = add_cumulative_columns(marginal)
        fixed_long_cumulative = fixed_long_marginal
    else:
        fixed_long_cumulative = build_fixed_costs_comparison(expense_df, through_actual)
        through_actual = attach_actual_net_profit(through_actual, fixed_long_cumulative)
        cumulative = add_cumulative_columns(through_actual)

    fixed_cumulative = add_fixed_costs_cumulative(fixed_long_cumulative)

    _render_comparison_tab(marginal, cumulative, fixed_long_marginal, fixed_cumulative)

    st.divider()

    _render_net_profit_charts(marginal, cumulative, sales, expense_df)

    st.caption(
        "Revenue & margin: red if variance < −15%, orange −15% to −5%, green ≥ −5%. "
        "Variable & fixed expenses: green < 5% over budget, orange 5–15%, red > 15%."
    )
