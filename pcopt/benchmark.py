"""Offline fixed-allocation benchmark evaluation and report rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import tempfile
from typing import Any

import numpy as np
import pandas as pd

from .currency import annual_fx_endpoints, convert_nominal_returns, deflate_returns
from .data import portfolio_returns
from .market_data import MarketDataset
from .metrics import annualized_return, metric_snapshot


CORE_ASSETS = (
    "USA-LCB", "USA-ITT", "USA-BIL", "CHN-A-CSI300", "CHN-GOV",
    "CHN-CASH", "HKG-HSI", "HKG-HSCEI", "GLO-GLD",
)


def metric_availability(observations: int) -> dict:
    if isinstance(observations, bool) or not isinstance(observations, int) or observations < 0:
        raise ValueError("observations must be a nonnegative integer")
    rows = {}
    for name, required in (
        ("rolling_cagr", 10), ("start_date_sensitivity", 20), ("withdrawal", 30)
    ):
        windows = max(0, observations - required + 1)
        item = {
            "status": "available" if windows else "unavailable",
            "required_years": required,
            "available_years": observations,
            "windows": windows,
            "overlapping": True,
        }
        if not windows:
            item["reason"] = "insufficient complete annual observations"
        rows[name] = item
    return rows


def _validate_requested_year(value: int | None, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"{name} must be an integer")


def _fx_pair_years(dataset: MarketDataset, candidate_years: Sequence[int]) -> set[int]:
    """Return years with complete previous/current year-end FX endpoint pairs."""
    annual_fx_endpoints(dataset.fx_daily, [])  # Validate the FX table itself once.
    valid = set()
    for year in candidate_years:
        try:
            annual_fx_endpoints(dataset.fx_daily, [year - 1, year])
        except ValueError as error:
            if "missing common FX endpoint" not in str(error):
                raise
        else:
            valid.add(year)
    return valid


def _select_common_years(
    dataset: MarketDataset,
    assets: Sequence[str],
    currencies: Sequence[str],
    *,
    start_year: int | None,
    end_year: int | None,
    as_of: date,
) -> tuple[list[int], dict[str, set[int]]]:
    _validate_requested_year(start_year, "start_year")
    _validate_requested_year(end_year, "end_year")
    if start_year is not None and end_year is not None and start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    for value, name in ((start_year, "start_year"), (end_year, "end_year")):
        if value is not None and value >= as_of.year:
            raise ValueError(
                f"{name} must be before as-of calendar year {as_of.year}"
            )
    if not assets:
        raise ValueError("at least one selected asset is required")
    unknown = sorted(set(assets) - set(dataset.nominal.columns))
    if unknown:
        raise ValueError("unknown asset: " + ", ".join(unknown))
    views = list(dict.fromkeys(currencies))
    if not views or any(currency not in {"USD", "CNY"} for currency in views):
        raise ValueError("currencies must contain USD and/or CNY")

    asset_rows = dataset.nominal.loc[:, list(dict.fromkeys(assets))]
    availability = {
        asset: set(asset_rows.index[asset_rows[asset].notna()].astype(int))
        for asset in asset_rows
    }
    for currency in views:
        if currency not in dataset.inflation.columns:
            availability[f"{currency} CPI"] = set()
        else:
            availability[f"{currency} CPI"] = set(
                dataset.inflation.index[dataset.inflation[currency].notna()].astype(int)
            )
    non_fx_years = set().union(*availability.values()) if availability else set()
    availability["FX endpoint pair"] = _fx_pair_years(
        dataset, sorted(year for year in non_fx_years if year < as_of.year)
    )
    empty = [name for name, values in availability.items() if not values]
    if empty:
        raise ValueError("empty common-year overlap: " + ", ".join(empty))
    lower = max(min(values) for values in availability.values())
    upper = min(min(max(values) for values in availability.values()), as_of.year - 1)
    if start_year is not None:
        lower = start_year
    if end_year is not None:
        upper = end_year
    if lower > upper:
        raise ValueError("empty common-year overlap")
    years = list(range(lower, upper + 1))

    for year in years:
        missing = [name for name, values in availability.items() if year not in values]
        if missing:
            qualifier = "explicit interval missing" if start_year is not None or end_year is not None else "internal gap"
            detail = f"{qualifier} at {year}: {', '.join(missing)}"
            if "FX endpoint pair" in missing:
                detail += f" (FX endpoint requirement failed for {year})"
            raise ValueError(detail)
    return years, availability


def select_common_years(
    dataset: MarketDataset,
    assets: Sequence[str],
    currencies: Sequence[str],
    *,
    start_year: int | None,
    end_year: int | None,
    as_of: date,
) -> list[int]:
    """Return one strict, consecutive interval shared by all requested inputs."""
    years, _ = _select_common_years(
        dataset,
        assets,
        currencies,
        start_year=start_year,
        end_year=end_year,
        as_of=as_of,
    )
    return years


def _validated_portfolios(dataset: MarketDataset, portfolios: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    if not isinstance(portfolios, Mapping) or not portfolios:
        raise ValueError("at least one portfolio is required")
    output = {}
    for name, raw in portfolios.items():
        if not isinstance(name, str) or not name or not isinstance(raw, Mapping) or not raw:
            raise ValueError("portfolio names and weight objects must be nonempty")
        clean = {}
        for asset, value in raw.items():
            if isinstance(value, bool) or not isinstance(value, (int, float, np.number)) or not math.isfinite(float(value)):
                raise ValueError(f"portfolio {name} weights must be finite numbers")
            value = float(value)
            if value < 0:
                raise ValueError(f"portfolio {name} weights must be nonnegative")
            if value != 0:
                clean[asset] = value
        if not clean:
            raise ValueError(f"portfolio {name} has zero total weight")
        unknown = sorted(set(clean) - set(dataset.nominal.columns))
        if unknown:
            raise ValueError(f"portfolio {name} contains unknown asset: {', '.join(unknown)}")
        if not math.isclose(sum(clean.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"portfolio {name} weights must sum to one")
        output[name] = clean
    return output


def _json_series(series: pd.Series) -> dict[str, float]:
    return {str(int(year)): float(value) for year, value in series.items()}


def _wealth(series: pd.Series) -> list[dict[str, Any]]:
    rows = [{"year": "initial", "value": 1.0}]
    wealth = (1.0 + series).cumprod()
    rows.extend({"year": int(year), "value": float(value)} for year, value in wealth.items())
    return rows


def _excluded_ranges(
    dataset: MarketDataset,
    years: list[int],
    as_of: date,
    availability: Mapping[str, set[int]],
    *,
    explicit_start: bool,
    explicit_end: bool,
) -> list[dict]:
    observed = sorted(int(year) for year in dataset.nominal.index if int(year) < as_of.year)
    rows = []
    if observed and observed[0] < years[0]:
        constraints = (
            ["explicit start_year"]
            if explicit_start
            else [name for name, values in availability.items() if min(values) == years[0]]
        )
        reason = "before common complete interval; constrained by " + ", ".join(constraints)
        rows.append({"start_year": observed[0], "end_year": years[0] - 1, "reason": reason})
    if observed and observed[-1] > years[-1]:
        constraints = (
            ["explicit end_year"]
            if explicit_end
            else [name for name, values in availability.items() if max(values) == years[-1]]
        )
        reason = "after common complete interval; constrained by " + ", ".join(constraints)
        rows.append({"start_year": years[-1] + 1, "end_year": observed[-1], "reason": reason})
    if any(int(year) >= as_of.year for year in dataset.nominal.index):
        rows.append({"start_year": as_of.year, "end_year": max(map(int, dataset.nominal.index)), "reason": "incomplete as-of calendar year or later"})
    return rows


def evaluate_benchmarks(
    dataset: MarketDataset,
    portfolios: Mapping[str, Mapping[str, float]],
    *,
    base_currency: str,
    start_year: int | None = None,
    end_year: int | None = None,
    as_of: date | None = None,
) -> dict:
    checked = _validated_portfolios(dataset, portfolios)
    if base_currency == "both":
        currencies = ["USD", "CNY"]
    elif base_currency in {"USD", "CNY"}:
        currencies = [base_currency]
    else:
        raise ValueError("base_currency must be USD, CNY, or both")
    covered_as_of_raw = dataset.manifest.get("coverage_as_of")
    covered_as_of = date.fromisoformat(covered_as_of_raw) if covered_as_of_raw else None
    if as_of is None and covered_as_of is None:
        raise ValueError("as_of is required when the manifest has no coverage_as_of")
    requested_as_of = as_of or covered_as_of
    assert requested_as_of is not None
    effective_as_of = min(requested_as_of, covered_as_of) if covered_as_of else requested_as_of
    assets = list(dict.fromkeys(asset for weights in checked.values() for asset in weights))
    years, availability = _select_common_years(
        dataset, assets, currencies, start_year=start_year, end_year=end_year, as_of=effective_as_of
    )
    endpoints = annual_fx_endpoints(dataset.fx_daily, [years[0] - 1, *years])
    local = dataset.nominal.loc[years, assets]
    asset_currencies = {asset: dataset.manifest["series"][asset]["currency"] for asset in assets}
    views = {}
    for currency in currencies:
        nominal_assets = convert_nominal_returns(local, asset_currencies, endpoints, currency)
        real_assets = deflate_returns(nominal_assets, dataset.inflation.loc[years, currency])
        view_portfolios = {}
        for name, weights in checked.items():
            nominal = portfolio_returns(nominal_assets, weights, missing="raise")
            real = portfolio_returns(real_assets, weights, missing="raise")
            nominal_metrics = metric_snapshot(nominal)
            real_metrics = metric_snapshot(real)
            view_portfolios[name] = {
                "weights": weights,
                "nominal_returns": _json_series(nominal),
                "real_returns": _json_series(real),
                "nominal_wealth": _wealth(nominal),
                "real_wealth": _wealth(real),
                "nominal_cumulative_return": float((1.0 + nominal).prod() - 1.0),
                "real_cumulative_return": float((1.0 + real).prod() - 1.0),
                "nominal_cagr": annualized_return(nominal),
                "real_cagr": annualized_return(real),
                "metrics": {"nominal": nominal_metrics, "real": real_metrics},
                "availability": metric_availability(len(years)),
                "risk_sampling": "annual year-end observations",
            }
        views[currency] = {"years": years, "inflation_basis": "December-over-December", "portfolios": view_portfolios}

    missing_core = sorted(set(CORE_ASSETS) - set(dataset.nominal.columns))
    full_core_years = []
    if not missing_core:
        try:
            full_core_years = select_common_years(dataset, CORE_ASSETS, ["USD", "CNY"], start_year=None, end_year=None, as_of=effective_as_of)
        except ValueError:
            full_core_years = []
    ready = dataset.manifest.get("data_kind") == "market" and not missing_core and len(full_core_years) >= 10
    argv = [
        "python", "-m", "pcopt.cli", "benchmark", "--manifest", "MANIFEST",
        "--weights", "WEIGHTS", "--base-currency", base_currency, "--output-dir", "OUTPUT_DIR",
        "--as-of", effective_as_of.isoformat(),
    ]
    if start_year is not None:
        argv.extend(["--start-year", str(start_year)])
    if end_year is not None:
        argv.extend(["--end-year", str(end_year)])
    endpoint_rows = [
        {
            "year": int(year),
            "observed_date": pd.Timestamp(row["observed_date"]).date().isoformat(),
            "CNY": float(row["CNY"]),
            "HKD": float(row["HKD"]),
        }
        for year, row in endpoints.iterrows()
    ]
    return {
        "schema_version": 1,
        "dataset_id": dataset.manifest.get("dataset_id"),
        "data_kind": dataset.manifest.get("data_kind"),
        "evaluation": {
            "as_of": effective_as_of.isoformat(), "years": years,
            "start_year": years[0], "end_year": years[-1], "observations": len(years),
            "excluded_ranges": _excluded_ranges(
                dataset,
                years,
                effective_as_of,
                availability,
                explicit_start=start_year is not None,
                explicit_end=end_year is not None,
            ),
            "rebalancing": "annual",
        },
        "source_assumptions": {
            "dataset": dataset.manifest.get("assumptions", []),
            "series": dataset.manifest.get("series", {}),
            "fees": "Per-series fee_basis and fee_notes; taxes are not modeled",
        },
        "provenance": {
            "fx": {
                "metadata": dataset.manifest.get("fx_metadata", {}),
                "selected_endpoints": endpoint_rows,
            },
            "inflation": {
                "metadata": dataset.manifest.get("inflation_metadata", {}),
                "selected_observations": {
                    currency: [
                        {"year": int(year), "inflation": float(dataset.inflation.at[year, currency])}
                        for year in years
                    ]
                    for currency in currencies
                },
            },
        },
        "coverage": dataset.manifest.get("coverage", {}),
        "views": views,
        "reproduce": {"argv": argv, "shell_display": shlex.join(argv)},
        "readiness": {
            "status": "ready" if ready else "incomplete",
            "required_core_assets": list(CORE_ASSETS),
            "missing_core_assets": missing_core,
            "minimum_complete_shared_years": 10,
            "complete_shared_years": len(full_core_years),
            "production_data_required": dataset.manifest.get("data_kind") != "market",
        },
    }


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")


def _percent(value: Any) -> str:
    return "—" if value is None else f"{float(value):.2%}"


def _compact(value: Any) -> str:
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_compact(item)}" for key, item in value.items())
    if isinstance(value, list):
        return "; ".join(_compact(item) for item in value)
    return str(value)


def _metric_or_reason(item: dict, key: str, availability_key: str) -> str:
    value = item["metrics"]["real"].get(key)
    if value is not None:
        return _percent(value)
    availability = item["availability"][availability_key]
    return f"Unavailable: {availability.get('reason', 'not calculated')} ({availability['available_years']}/{availability['required_years']} years)"


def render_benchmark_markdown(report: dict) -> str:
    years = report["evaluation"]["years"]
    lines = [
        "# Fixed-allocation benchmark report", "",
        f"Dataset: `{_escape(report['dataset_id'])}`  ",
        f"Evaluation years: {years[0]}–{years[-1]} ({len(years)} complete annual observations)  ",
        "Risk sampling: Year-end risk from annual observations.  ",
        f"Readiness: **{_escape(report['readiness']['status'])}**", "",
        "## Portfolio definitions", "",
        "| Portfolio | Weights | Series IDs |", "|---|---|---|",
    ]
    definitions = next(iter(report["views"].values()))["portfolios"]
    series = report["source_assumptions"]["series"]
    for name, item in definitions.items():
        weights = "; ".join(f"{asset}: {weight:.2%}" for asset, weight in item["weights"].items())
        series_ids = "; ".join(
            f"{asset}: {series.get(asset, {}).get('series_id', '')}" for asset in item["weights"]
        )
        lines.append(f"| {_escape(name)} | {_escape(weights)} | {_escape(series_ids)} |")
    lines.append("")
    for currency, view in report["views"].items():
        lines.extend([
            f"## {currency} purchasing-power view", "",
            "| Portfolio | Nominal cumulative return | Real cumulative return | Nominal CAGR | Real CAGR | Real volatility | Deepest drawdown | Ulcer index |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for name, item in view["portfolios"].items():
            metrics = item["metrics"]["real"]
            lines.append(
                f"| {_escape(name)} | {_percent(item['nominal_cumulative_return'])} | {_percent(item['real_cumulative_return'])} | "
                f"{_percent(item['nominal_cagr'])} | {_percent(item['real_cagr'])} | "
                f"{_percent(metrics.get('standard_deviation'))} | {_percent(metrics.get('deepest_drawdown'))} | "
                f"{_percent(metrics.get('ulcer_index'))} |"
            )
        lines.extend(["", "### Horizon metrics", "",
                      "| Portfolio | Windows (10y / 20y / 30y) | Rolling CAGR min / 15th / median / 85th / max | Start-date sensitivity | SWR / PWR / LTWR |",
                      "|---|---|---|---|---|"])
        for name, item in view["portfolios"].items():
            metrics = item["metrics"]["real"]
            available = item["availability"]
            windows = (
                f"10y: {available['rolling_cagr']['windows']}; "
                f"20y: {available['start_date_sensitivity']['windows']}; "
                f"30y: {available['withdrawal']['windows']}"
            )
            rolling = " / ".join(_percent(metrics.get(key)) for key in (
                "rolling_cagr_min", "rolling_cagr_baseline", "rolling_cagr_median",
                "rolling_cagr_stretch", "rolling_cagr_max",
            )) if "rolling_cagr_min" in metrics else _metric_or_reason(item, "rolling_cagr_min", "rolling_cagr")
            sensitivity = _metric_or_reason(item, "start_date_sensitivity", "start_date_sensitivity")
            withdrawals = " / ".join(_percent(metrics.get(key)) for key in (
                "safe_withdrawal_rate", "perpetual_withdrawal_rate", "long_term_withdrawal_rate",
            )) if "safe_withdrawal_rate" in metrics else _metric_or_reason(item, "safe_withdrawal_rate", "withdrawal")
            lines.append(f"| {_escape(name)} | {windows} | {_escape(rolling)} | {_escape(sensitivity)} | {_escape(withdrawals)} |")
        lines.extend(["", "Rolling CAGR values are min / 15th percentile / median / 85th percentile / max. Withdrawal values are SWR / PWR / LTWR. Windows are overlapping.", ""])
    fx = report.get("provenance", {}).get("fx", {})
    lines.extend(["## FX and inflation provenance", "", f"FX metadata: {_escape(_compact(fx.get('metadata', {})))}", "",
                  "| Endpoint year | Observed date | CNY per USD | HKD per USD |", "|---:|---|---:|---:|"])
    for endpoint in fx.get("selected_endpoints", []):
        lines.append(f"| {endpoint['year']} | {endpoint['observed_date']} | {endpoint['CNY']:.6g} | {endpoint['HKD']:.6g} |")
    inflation = report.get("provenance", {}).get("inflation", {})
    lines.extend(["", f"Inflation metadata: {_escape(_compact(inflation.get('metadata', {})))}", ""])
    for currency, observations in inflation.get("selected_observations", {}).items():
        selected = "; ".join(f"{row['year']}: {row['inflation']:.4%}" for row in observations)
        lines.append(f"{currency} selected CPI changes: {_escape(selected)}")
    lines.append("")
    lines.extend(["## Dataset assumptions", ""])
    assumptions = report["source_assumptions"].get("dataset", [])
    lines.extend(f"- {_escape(assumption)}" for assumption in assumptions)
    if not assumptions:
        lines.append("None declared.")
    lines.extend(["", "## Coverage and readiness", "", "| Field | Value |", "|---|---|"])
    for key, value in report.get("coverage", {}).items():
        lines.append(f"| {_escape(key)} | {_escape(_compact(value))} |")
    readiness = report["readiness"]
    lines.append(f"| Missing core assets | {_escape('; '.join(readiness['missing_core_assets']) or 'None')} |")
    lines.append(f"| Full core universe shared years | {readiness['complete_shared_years']} / {readiness['minimum_complete_shared_years']} required |")
    lines.extend(["", "## Source, fee, and backfill caveats", "", "| Asset | Source | Fee basis | Fee notes | Backfill | Limitations |", "|---|---|---|---|---|---|"])
    for asset, metadata in report["source_assumptions"]["series"].items():
        limits = "; ".join(metadata.get("limitations", []))
        lines.append(
            f"| {_escape(asset)} | {_escape(metadata.get('source_id', ''))} | {_escape(metadata.get('fee_basis', ''))} | "
            f"{_escape(metadata.get('fee_notes', ''))} | {_escape(metadata.get('backfill_start_date') or 'none declared')} | {_escape(limits)} |"
        )
    lines.extend(["", "## Excluded years", ""])
    excluded = report["evaluation"]["excluded_ranges"]
    if excluded:
        lines.extend(["| Years | Reason |", "|---|---|"])
        for item in excluded:
            lines.append(f"| {item['start_year']}–{item['end_year']} | {_escape(item['reason'])} |")
    else:
        lines.append("None.")
    lines.extend(["", "## Regeneration", "", f"`{_escape(report['reproduce']['shell_display'])}`", ""])
    return "\n".join(lines)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_benchmark_report(
    report: dict, output_dir: str | Path, *, allow_synthetic_demo: bool = False
) -> None:
    if report.get("data_kind") != "market" and not allow_synthetic_demo:
        raise ValueError("synthetic datasets require explicit demo opt-in")
    root = Path(output_dir)
    json_bytes = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    markdown_bytes = render_benchmark_markdown(report).encode("utf-8")
    # Complete validation occurs before either target is replaced.
    json.loads(json_bytes)
    markdown_bytes.decode("utf-8")
    provenance = {
        "schema_version": 1,
        "dataset_id": report.get("dataset_id"),
        "artifacts": {
            "benchmark.json": hashlib.sha256(json_bytes).hexdigest(),
            "benchmark.md": hashlib.sha256(markdown_bytes).hexdigest(),
        },
    }
    provenance_bytes = (json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    _atomic_write(root / "benchmark.json", json_bytes)
    _atomic_write(root / "benchmark.md", markdown_bytes)
    _atomic_write(root / "benchmark.provenance.json", provenance_bytes)
