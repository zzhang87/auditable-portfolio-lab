import json
import os
from datetime import date

import pandas as pd
import pytest

from pcopt.market_data import MarketDataset

CORE = [
    "USA-LCB",
    "USA-ITT",
    "USA-BIL",
    "CHN-A-CSI300",
    "CHN-GOV",
    "CHN-CASH",
    "HKG-HSI",
    "HKG-HSCEI",
    "GLO-GLD",
]


def _dataset(*, years=range(2010, 2025), missing=None, data_kind="synthetic_test"):
    years = list(years)
    nominal = pd.DataFrame(
        {
            asset: [0.04 + (i % 4) * 0.01 + position * 0.001 for i in range(len(years))]
            for position, asset in enumerate(CORE)
        },
        index=years,
    )
    if missing:
        nominal.loc[missing[1], missing[0]] = float("nan")
    fx_years = range(min(years) - 1, max(years) + 1)
    fx = pd.DataFrame(
        {
            "CNY": [6.7 + 0.02 * i for i, _ in enumerate(fx_years)],
            "HKD": [7.75 + 0.003 * i for i, _ in enumerate(fx_years)],
        },
        index=pd.to_datetime([f"{year}-12-31" for year in fx_years]),
    )
    inflation = pd.DataFrame({"USD": [0.02] * len(years), "CNY": [0.025] * len(years)}, index=years)
    currencies = {
        asset: ("CNY" if asset.startswith("CHN") else "HKD" if asset.startswith("HKG") else "USD") for asset in CORE
    }
    series = {
        asset: {
            "asset_id": asset,
            "currency": currencies[asset],
            "source_id": "synthetic",
            "fee_basis": "gross_of_fund_fees",
            "fee_notes": "Synthetic | test\nonly",
            "backfill_start_date": None,
            "limitations": ["Synthetic test data only"],
        }
        for asset in CORE
    }
    manifest = {
        "schema_version": 1,
        "dataset_id": "synthetic-id",
        "data_kind": data_kind,
        "series": series,
        "coverage": {"required_assets": ["USA-LCB"], "minimum_shared_years": 1},
        "coverage_as_of": "2026-09-19",
        "fx_metadata": {
            "quote_orientation": "units_per_USD",
            "observation_timing": "close",
            "series": {"CNY": "observed", "HKD": "observed"},
        },
        "inflation_metadata": {
            "USD": {
                "geography": "United States",
                "seasonal_adjustment": "not seasonally adjusted",
                "units": "decimal_change",
                "basis": "December-over-December",
            },
            "CNY": {
                "geography": "China",
                "seasonal_adjustment": "not seasonally adjusted",
                "units": "decimal_change",
                "basis": "December-over-December",
            },
        },
        "assumptions": ["Annual rebalancing", "No taxes"],
    }
    return MarketDataset(manifest, nominal, fx, inflation, pd.DataFrame())


PORTFOLIOS = {
    "global": {"USA-LCB": 0.5, "CHN-A-CSI300": 0.3, "HKG-HSI": 0.2},
    "ignored_zero": {"USA-ITT": 1.0, "MISSING": 0.0},
}


def test_metric_availability_counts_full_windows():
    from pcopt.benchmark import metric_availability

    result = metric_availability(15)
    assert result["rolling_cagr"]["windows"] == 6
    assert result["rolling_cagr"]["overlapping"] is True
    assert result["withdrawal"] == {
        "status": "unavailable",
        "required_years": 30,
        "available_years": 15,
        "windows": 0,
        "overlapping": True,
        "reason": "insufficient complete annual observations",
    }


def test_both_views_share_exact_years_weights_and_hand_checked_conversion():
    from pcopt.benchmark import evaluate_benchmarks

    report = evaluate_benchmarks(_dataset(), PORTFOLIOS, base_currency="both", as_of=date(2026, 1, 1))
    assert report["evaluation"]["years"] == list(range(2010, 2025))
    assert report["views"]["USD"]["years"] == report["views"]["CNY"]["years"]
    assert report["views"]["USD"]["portfolios"]["global"]["weights"] == PORTFOLIOS["global"]
    assert report["views"]["CNY"]["portfolios"]["global"]["weights"] == PORTFOLIOS["global"]
    # 2010 local returns: USD .04, CNY .043, HKD .046. USD conversions use q0/q1.
    expected = 0.5 * 0.04 + 0.3 * ((1.043 * 6.7 / 6.72) - 1) + 0.2 * ((1.046 * 7.75 / 7.753) - 1)
    assert report["views"]["USD"]["portfolios"]["global"]["nominal_returns"]["2010"] == pytest.approx(expected)
    assert len(report["views"]["USD"]["portfolios"]["global"]["nominal_wealth"]) == 16
    assert report["views"]["USD"]["portfolios"]["global"]["availability"]["withdrawal"]["status"] == "unavailable"
    assert report["evaluation"]["as_of"] == "2026-01-01"
    assert report["provenance"]["fx"]["selected_endpoints"][0] == {
        "year": 2009,
        "observed_date": "2009-12-31",
        "CNY": 6.7,
        "HKD": 7.75,
    }
    assert report["provenance"]["fx"]["metadata"]["quote_orientation"] == "units_per_USD"
    assert report["provenance"]["inflation"]["metadata"]["CNY"]["geography"] == "China"


def test_identity_cutoff_prevents_clock_rollover_from_admitting_partial_row():
    from pcopt.benchmark import evaluate_benchmarks

    dataset = _dataset(years=range(2015, 2027))
    before = evaluate_benchmarks(dataset, {"us": {"USA-LCB": 1.0}}, base_currency="USD", as_of=date(2026, 9, 19))
    after = evaluate_benchmarks(dataset, {"us": {"USA-LCB": 1.0}}, base_currency="USD", as_of=date(2027, 1, 1))
    assert before == after
    assert after["evaluation"]["end_year"] == 2025
    assert after["reproduce"]["argv"][-2:] == ["--as-of", "2026-09-19"]


def test_evaluator_requires_cutoff_when_manifest_has_no_coverage_cutoff():
    from pcopt.benchmark import evaluate_benchmarks

    dataset = _dataset()
    dataset.manifest.pop("coverage_as_of")
    with pytest.raises(ValueError, match="as_of.*coverage_as_of"):
        evaluate_benchmarks(dataset, {"us": {"USA-LCB": 1.0}}, base_currency="USD")


def test_common_year_selection_rejects_internal_gap_and_exact_shortening():
    from pcopt.benchmark import select_common_years

    dataset = _dataset(missing=("USA-LCB", 2017))
    with pytest.raises(ValueError, match="internal gap.*2017"):
        select_common_years(
            dataset, ["USA-LCB"], ["USD", "CNY"], start_year=None, end_year=None, as_of=date(2026, 1, 1)
        )
    with pytest.raises(ValueError, match="explicit.*2017"):
        select_common_years(dataset, ["USA-LCB"], ["USD"], start_year=2015, end_year=2019, as_of=date(2026, 1, 1))


@pytest.mark.parametrize(
    "weights, message",
    [
        ({"USA-LCB": float("nan")}, "finite"),
        ({"USA-LCB": -0.1, "USA-ITT": 1.1}, "nonnegative"),
        ({"USA-LCB": 0.4}, "sum to one"),
        ({"USA-LCB": 0.0}, "zero"),
        ({"UNKNOWN": 1.0}, "unknown asset"),
    ],
)
def test_invalid_weights_are_rejected(weights, message):
    from pcopt.benchmark import evaluate_benchmarks

    with pytest.raises(ValueError, match=message):
        evaluate_benchmarks(_dataset(), {"bad": weights}, base_currency="USD", as_of=date(2026, 1, 1))


def test_readiness_requires_full_fixed_core_universe_despite_coverage_metadata():
    from pcopt.benchmark import evaluate_benchmarks

    dataset = _dataset()
    dataset = MarketDataset(
        dataset.manifest,
        dataset.nominal.drop(columns="HKG-HSCEI"),
        dataset.fx_daily,
        dataset.inflation,
        dataset.references,
    )
    report = evaluate_benchmarks(dataset, {"us": {"USA-LCB": 1.0}}, base_currency="USD", as_of=date(2026, 1, 1))
    assert report["readiness"]["status"] == "incomplete"
    assert "HKG-HSCEI" in report["readiness"]["missing_core_assets"]


def test_markdown_escapes_metadata_and_writer_requires_demo_opt_in(tmp_path):
    from pcopt.benchmark import evaluate_benchmarks, render_benchmark_markdown, write_benchmark_report

    report = evaluate_benchmarks(_dataset(), {"us": {"USA-LCB": 1.0}}, base_currency="USD", as_of=date(2026, 1, 1))
    markdown = render_benchmark_markdown(report)
    assert "Synthetic \\| test<br>only" in markdown
    assert "Year-end risk" in markdown
    assert "USA-LCB: 100.00%" in markdown
    assert "synthetic" in markdown
    assert "Real cumulative return" in markdown
    assert "Ulcer index" in markdown
    assert "Rolling CAGR" in markdown
    assert "insufficient complete annual observations" in markdown
    assert "Missing core assets" in markdown
    assert "Annual rebalancing" in markdown
    assert "2009-12-31" in markdown
    assert "United States" in markdown
    assert "2010: 2.0000%" in markdown
    assert "10y: 6; 20y: 0; 30y: 0" in markdown
    with pytest.raises(ValueError, match="synthetic"):
        write_benchmark_report(report, tmp_path)
    write_benchmark_report(report, tmp_path, allow_synthetic_demo=True)
    parsed = json.loads((tmp_path / "benchmark.json").read_text())
    assert parsed["dataset_id"] == "synthetic-id"
    provenance = json.loads((tmp_path / "benchmark.provenance.json").read_text())
    assert set(provenance["artifacts"]) == {"benchmark.json", "benchmark.md"}


def test_writer_identical_replay_preserves_artifact_bytes_and_metadata(tmp_path):
    from pcopt.benchmark import evaluate_benchmarks, write_benchmark_report

    report = evaluate_benchmarks(_dataset(), PORTFOLIOS, base_currency="both", as_of=date(2026, 1, 1))
    write_benchmark_report(report, tmp_path, allow_synthetic_demo=True)
    for path in tmp_path.iterdir():
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    before = {
        path.name: (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns) for path in tmp_path.iterdir()
    }

    write_benchmark_report(report, tmp_path, allow_synthetic_demo=True)

    after = {path.name: (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns) for path in tmp_path.iterdir()}
    assert after == before


@pytest.mark.parametrize("conflict", ["benchmark.json", "benchmark.md", "benchmark.provenance.json"])
@pytest.mark.parametrize("missing_sibling", [False, True])
def test_writer_conflicting_replay_preserves_every_existing_artifact(tmp_path, conflict, missing_sibling):
    from pcopt.benchmark import evaluate_benchmarks, write_benchmark_report

    report = evaluate_benchmarks(_dataset(), PORTFOLIOS, base_currency="both", as_of=date(2026, 1, 1))
    write_benchmark_report(report, tmp_path, allow_synthetic_demo=True)
    (tmp_path / conflict).write_bytes(b"previous evidence must survive\n")
    if missing_sibling:
        next(path for path in tmp_path.iterdir() if path.name != conflict).unlink()
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    with pytest.raises(FileExistsError) as error:
        write_benchmark_report(report, tmp_path, allow_synthetic_demo=True)

    assert conflict in str(error.value)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_writer_changed_weights_rejects_replay_and_preserves_previous_evidence(tmp_path):
    from pcopt.benchmark import evaluate_benchmarks, write_benchmark_report

    original = evaluate_benchmarks(_dataset(), PORTFOLIOS, base_currency="both", as_of=date(2026, 1, 1))
    write_benchmark_report(original, tmp_path, allow_synthetic_demo=True)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    changed = evaluate_benchmarks(
        _dataset(), {"global": {"USA-LCB": 1.0}}, base_currency="both", as_of=date(2026, 1, 1)
    )

    with pytest.raises(FileExistsError) as error:
        write_benchmark_report(changed, tmp_path, allow_synthetic_demo=True)

    assert all(name in str(error.value) for name in before)
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_writer_identical_replay_restores_missing_artifact(tmp_path):
    from pcopt.benchmark import evaluate_benchmarks, write_benchmark_report

    report = evaluate_benchmarks(_dataset(), PORTFOLIOS, base_currency="both", as_of=date(2026, 1, 1))
    write_benchmark_report(report, tmp_path, allow_synthetic_demo=True)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    (tmp_path / "benchmark.md").unlink()

    write_benchmark_report(report, tmp_path, allow_synthetic_demo=True)

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_markdown_renders_available_long_horizon_metrics_and_coverage_reasons():
    from pcopt.benchmark import evaluate_benchmarks, render_benchmark_markdown

    dataset = _dataset(years=range(1985, 2025))
    dataset.manifest["coverage"]["unavailable_assets"] = {"HKG-HSCEI": "usable total-return history was not acquired"}
    report = evaluate_benchmarks(
        dataset,
        {"Arbitrary retirement mix": {"USA-LCB": 0.7, "USA-ITT": 0.3}},
        base_currency="USD",
        as_of=date(2026, 1, 1),
    )
    markdown = render_benchmark_markdown(report)
    assert "Arbitrary retirement mix" in markdown
    assert "Unavailable: insufficient" not in markdown
    assert "usable total-return history was not acquired" in markdown
    assert "10y: 31; 20y: 21; 30y: 11" in markdown


def test_stale_fx_and_current_incomplete_year_are_rejected_or_excluded():
    from pcopt.benchmark import select_common_years

    dataset = _dataset(years=range(2023, 2027))
    assert select_common_years(
        dataset, ["USA-LCB"], ["USD"], start_year=None, end_year=None, as_of=date(2026, 9, 19)
    ) == [2023, 2024, 2025]
    stale = dataset.fx_daily.drop(pd.Timestamp("2024-12-31"))
    dataset = MarketDataset(dataset.manifest, dataset.nominal, stale, dataset.inflation, dataset.references)
    with pytest.raises(ValueError, match="FX endpoint.*2024"):
        select_common_years(dataset, ["USA-LCB"], ["USD"], start_year=2024, end_year=2025, as_of=date(2026, 9, 19))


def test_explicit_current_or_future_year_is_rejected_before_selection():
    from pcopt.benchmark import select_common_years

    dataset = _dataset(years=range(2023, 2028))
    with pytest.raises(ValueError, match="end_year.*as-of.*2026"):
        select_common_years(
            dataset,
            ["USA-LCB"],
            ["USD"],
            start_year=2025,
            end_year=2026,
            as_of=date(2026, 9, 19),
        )


def test_automatic_interval_intersects_fx_pair_boundary_but_explicit_range_does_not_trim():
    from pcopt.benchmark import select_common_years

    dataset = _dataset(years=range(2010, 2015))
    without_initial_endpoint = dataset.fx_daily.drop(pd.Timestamp("2009-12-31"))
    dataset = MarketDataset(
        dataset.manifest,
        dataset.nominal,
        without_initial_endpoint,
        dataset.inflation,
        dataset.references,
    )

    assert select_common_years(
        dataset,
        ["USA-LCB"],
        ["USD"],
        start_year=None,
        end_year=None,
        as_of=date(2026, 1, 1),
    ) == [2011, 2012, 2013, 2014]
    with pytest.raises(ValueError, match="explicit interval missing.*2010.*FX endpoint pair"):
        select_common_years(
            dataset,
            ["USA-LCB"],
            ["USD"],
            start_year=2010,
            end_year=2014,
            as_of=date(2026, 1, 1),
        )


def test_excluded_boundary_reason_names_constraining_input():
    from pcopt.benchmark import evaluate_benchmarks

    dataset = _dataset(years=range(2010, 2015))
    without_initial_endpoint = dataset.fx_daily.drop(pd.Timestamp("2009-12-31"))
    dataset = MarketDataset(
        dataset.manifest,
        dataset.nominal,
        without_initial_endpoint,
        dataset.inflation,
        dataset.references,
    )

    report = evaluate_benchmarks(
        dataset,
        {"us": {"USA-LCB": 1.0}},
        base_currency="USD",
        as_of=date(2026, 1, 1),
    )
    assert report["evaluation"]["excluded_ranges"][0] == {
        "start_year": 2010,
        "end_year": 2010,
        "reason": "before common complete interval; constrained by FX endpoint pair",
    }
