"""Static, reproducible visual summaries of benchmark reports."""

import json
from pathlib import Path

import numpy as np

_BLUE = "#0072B2"
_ORANGE = "#E69F00"


def _series_values(series: list[dict[str, float | int | str]]) -> tuple[list[int], np.ndarray]:
    """Return the observed years and real-wealth values, excluding the baseline."""
    observations = [point for point in series if point["year"] != "initial"]
    return [int(point["year"]) for point in observations], np.array([point["value"] for point in observations])


def render_benchmark_overview(report_path: Path, output_path: Path) -> Path:
    """Render a deterministic four-panel overview from a benchmark JSON report."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    report = json.loads(report_path.read_text(encoding="utf-8"))
    views = report.get("views", {})
    if "USD" not in views or "CNY" not in views:
        raise ValueError("benchmark report must contain both USD and CNY views")

    usd_portfolios = views["USD"].get("portfolios", {})
    cny_portfolios = views["CNY"].get("portfolios", {})
    if not usd_portfolios or not cny_portfolios:
        raise ValueError("benchmark report must contain portfolios in both currency views")

    portfolio = sorted(usd_portfolios)[0]
    if portfolio not in cny_portfolios:
        raise ValueError(f"portfolio {portfolio!r} is missing from the CNY view")

    usd = usd_portfolios[portfolio]
    cny = cny_portfolios[portfolio]
    years, usd_real = _series_values(usd["real_wealth"])
    cny_years, cny_real = _series_values(cny["real_wealth"])
    if years != cny_years:
        raise ValueError("USD and CNY real-wealth series must use matching years")

    drawdown = usd_real / np.maximum.accumulate(usd_real) - 1
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    fig.subplots_adjust(left=0.06, right=0.985, bottom=0.10, top=0.89, hspace=0.46, wspace=0.12)
    fig.suptitle("Auditable Portfolio Lab - Synthetic Demo", y=0.965, fontsize=16, fontweight="bold")

    wealth_ax = axes[0, 0]
    wealth_ax.plot(years, usd_real, color=_BLUE, linewidth=2.5, label="USD real wealth")
    wealth_ax.set_title("Real Wealth")
    wealth_ax.set_ylabel("Growth of $1")
    wealth_ax.grid(axis="y", alpha=0.25)
    wealth_ax.legend(frameon=False)

    drawdown_ax = axes[0, 1]
    drawdown_ax.fill_between(years, drawdown, 0, color=_ORANGE, alpha=0.8)
    drawdown_ax.plot(years, drawdown, color=_ORANGE, linewidth=2)
    drawdown_ax.set_title("USD Real-Wealth Drawdown")
    drawdown_ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    drawdown_ax.grid(axis="y", alpha=0.25)

    purchasing_power_ax = axes[1, 0]
    currencies = ["USD", "CNY"]
    terminal_wealth = [usd_real[-1], cny_real[-1]]
    bars = purchasing_power_ax.bar(currencies, terminal_wealth, color=[_BLUE, _ORANGE], width=0.55)
    purchasing_power_ax.set_title("Terminal Purchasing Power")
    purchasing_power_ax.set_ylabel("Real wealth, growth of 1")
    purchasing_power_ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, terminal_wealth, strict=True):
        purchasing_power_ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.2f}x",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    readiness = report.get("readiness", {})
    coverage = report.get("coverage", {})
    summary_ax = axes[1, 1]
    summary_ax.axis("off")
    summary_ax.set_title("Readiness & Provenance", loc="left")
    missing = readiness.get("missing_core_assets", [])
    summary_lines = [
        f"Portfolio: {portfolio}",
        f"Data: {report.get('data_kind', 'unknown')}",
        f"Window: {years[0]}–{years[-1]} ({len(years)} annual observations)",
        f"Shared history: {coverage.get('complete_shared_years', 'n/a')} years",
        f"Production readiness: {readiness.get('status', 'unknown')}",
        f"Missing core assets: {len(missing)}",
        "Annual rebalancing; taxes and costs excluded.",
    ]
    summary_ax.text(
        0,
        0.96,
        "\n".join(summary_lines),
        transform=summary_ax.transAxes,
        va="top",
        fontsize=10.5,
        linespacing=1.6,
        bbox={"boxstyle": "round,pad=0.6", "facecolor": "#F5F5F5", "edgecolor": "#999999"},
    )

    fig.text(0.5, 0.025, "Synthetic demonstration data - not investment advice", ha="center", fontsize=9)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, metadata={"Creation Time": None, "Date": None})
    plt.close(fig)
    return output_path
