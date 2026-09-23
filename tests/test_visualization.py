import copy
import json
from pathlib import Path

import pytest


def _demo_report() -> dict:
    return json.loads(Path("examples/demo/expected/benchmark.json").read_text(encoding="utf-8"))


def _write_report(tmp_path, report: dict) -> Path:
    report_path = tmp_path / "benchmark.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return report_path


def test_visualization_module_is_lazy_and_writes_png(tmp_path):
    from pcopt.visualization import render_benchmark_overview

    output = render_benchmark_overview(
        Path("examples/demo/expected/benchmark.json"),
        tmp_path / "overview.png",
    )
    assert output == tmp_path / "overview.png"
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 20_000


def test_core_import_does_not_load_matplotlib():
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-c", "import pcopt, sys; print('matplotlib' in sys.modules)"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "False"


def test_renderer_drawdown_includes_initial_wealth(tmp_path, monkeypatch):
    from matplotlib.figure import Figure

    from pcopt.visualization import render_benchmark_overview

    report = _demo_report()
    for currency in ("USD", "CNY"):
        report["views"][currency]["portfolios"]["balanced_demo"]["real_wealth"] = [
            {"year": "initial", "value": 1.0},
            {"year": 2015, "value": 0.8},
            {"year": 2016, "value": 0.88},
        ]
    rendered_drawdown = []
    savefig = Figure.savefig

    def capture_drawdown(figure, *args, **kwargs):
        rendered_drawdown.extend(figure.axes[1].lines[0].get_ydata())
        return savefig(figure, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", capture_drawdown)
    render_benchmark_overview(_write_report(tmp_path, report), tmp_path / "overview.png")

    assert rendered_drawdown == pytest.approx([-0.2, -0.12])


@pytest.mark.parametrize("currency", ["USD", "CNY"])
def test_renderer_rejects_report_missing_required_currency_view(tmp_path, currency):
    from pcopt.visualization import render_benchmark_overview

    report = _demo_report()
    del report["views"][currency]

    with pytest.raises(ValueError, match="both USD and CNY views"):
        render_benchmark_overview(_write_report(tmp_path, report), tmp_path / "overview.png")


def test_renderer_rejects_selected_usd_portfolio_absent_from_cny(tmp_path):
    from pcopt.visualization import render_benchmark_overview

    report = _demo_report()
    portfolio = report["views"]["USD"]["portfolios"].pop("balanced_demo")
    report["views"]["USD"]["portfolios"] = {"alpha": portfolio}
    report["views"]["CNY"]["portfolios"] = {"beta": copy.deepcopy(portfolio)}

    with pytest.raises(ValueError, match="portfolio 'alpha' is missing from the CNY view"):
        render_benchmark_overview(_write_report(tmp_path, report), tmp_path / "overview.png")


def test_renderer_rejects_differing_usd_and_cny_real_wealth_years(tmp_path):
    from pcopt.visualization import render_benchmark_overview

    report = _demo_report()
    report["views"]["CNY"]["portfolios"]["balanced_demo"]["real_wealth"][-1]["year"] = 2026

    with pytest.raises(ValueError, match="matching years"):
        render_benchmark_overview(_write_report(tmp_path, report), tmp_path / "overview.png")


def test_renderer_uses_first_sorted_usd_portfolio(tmp_path):
    from pcopt.visualization import render_benchmark_overview

    report = _demo_report()
    portfolio = report["views"]["USD"]["portfolios"]["balanced_demo"]
    report["views"]["USD"]["portfolios"] = {"beta": copy.deepcopy(portfolio), "alpha": portfolio}
    report["views"]["CNY"]["portfolios"] = {"alpha": copy.deepcopy(portfolio)}

    output = render_benchmark_overview(_write_report(tmp_path, report), tmp_path / "overview.png")

    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
