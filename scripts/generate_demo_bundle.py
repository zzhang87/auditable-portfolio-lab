from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from pcopt.market_data import dataset_identity

LIMITATION = "Synthetic demonstration data; not historical market evidence"
GROWTH = [0.08, -0.04, 0.14, -0.09, 0.18, 0.11, 0.06, -0.15, 0.12, 0.09, 0.07]
DEFENSIVE = [0.025, 0.018, 0.022, 0.015, 0.028, 0.031, -0.01, -0.06, 0.035, 0.027, 0.024]
CNY_PER_USD = [6.12, 6.49, 6.94, 6.51, 6.88, 6.96, 6.53, 6.37, 6.90, 7.10, 7.30, 6.99]
HKD_PER_USD = [7.75, 7.75, 7.75, 7.81, 7.83, 7.79, 7.75, 7.80, 7.80, 7.81, 7.77, 7.78]
USD_INFLATION = [0.001, 0.021, 0.021, 0.019, 0.023, 0.014, 0.070, 0.065, 0.034, 0.029, 0.027]
CNY_INFLATION = [0.016, 0.021, 0.018, 0.019, 0.045, 0.002, 0.015, 0.018, -0.003, 0.001, 0.008]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, header: list[str], rows: list[tuple]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def series_metadata(asset_id: str, family: str, exposure: str) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "series_id": f"{asset_id}-TR",
        "source_id": "REPOSITORY-AUTHORED-SYNTHETIC-DEMO",
        "source_url": "https://github.com/zzhang87/auditable-portfolio-lab/tree/main/examples/demo",
        "methodology_url": "https://github.com/zzhang87/auditable-portfolio-lab/blob/main/docs/data-and-limitations.md",
        "listing_market": "synthetic",
        "economic_exposure": exposure,
        "asset_family": family,
        "currency": "USD",
        "return_kind": "gross_total_return",
        "fee_basis": "gross_of_fund_fees",
        "fee_notes": "No fees; repository-authored synthetic demonstration series",
        "hedge_status": "unhedged",
        "is_proxy": True,
        "launch_date": None,
        "backfill_start_date": None,
        "frequency": "annual",
        "annualization_recipe": "fixed repository-authored annual demonstration values",
        "period_end_convention": "synthetic calendar-year return",
        "first_year": 2015,
        "last_year": 2025,
        "status": "validated",
        "limitations": [LIMITATION],
    }


def generate_demo_bundle(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    returns = {"DEMO-GROWTH": GROWTH, "DEMO-DEFENSIVE": DEFENSIVE}
    write_csv(
        output / "annual_nominal.csv",
        ["year", "asset_id", "series_id", "nominal_return"],
        [
            (year, asset, f"{asset}-TR", values[year - 2015])
            for year in range(2015, 2026)
            for asset, values in returns.items()
        ],
    )
    write_csv(
        output / "fx_daily.csv",
        ["date", "CNY", "HKD"],
        [
            (f"{year}-12-31", cny, hkd)
            for year, cny, hkd in zip(range(2014, 2026), CNY_PER_USD, HKD_PER_USD, strict=True)
        ],
    )
    write_csv(
        output / "inflation.csv",
        ["year", "USD", "CNY"],
        list(zip(range(2015, 2026), USD_INFLATION, CNY_INFLATION, strict=True)),
    )
    evidence_path = output / "evidence.txt"
    evidence_rows = [
        (asset, year, values[year - 2015]) for asset, values in returns.items() for year in (2015, 2020, 2025)
    ]
    evidence_path.write_text(
        LIMITATION
        + "\nRepository-authored fixed reference values (CC0-1.0).\n"
        + "".join(f"{asset},{year},{value}\n" for asset, year, value in evidence_rows),
        encoding="utf-8",
    )
    write_csv(
        output / "references.csv",
        ["asset_id", "year", "expected_return", "absolute_tolerance", "evidence_path", "evidence_sha256"],
        [(asset, year, value, 0.000001, "evidence.txt", sha256(evidence_path)) for asset, year, value in evidence_rows],
    )
    manifest = {
        "schema_version": 1,
        "transformation_version": "synthetic-demo-v1",
        "data_kind": "synthetic_test",
        "coverage_as_of": "2026-01-01",
        "series": {
            "DEMO-GROWTH": series_metadata("DEMO-GROWTH", "equity", "Synthetic growth assets"),
            "DEMO-DEFENSIVE": series_metadata("DEMO-DEFENSIVE", "bond", "Synthetic defensive assets"),
        },
        "coverage": {
            "required_assets": ["DEMO-GROWTH", "DEMO-DEFENSIVE"],
            "minimum_shared_years": 10,
            "first_complete_year": 2015,
            "latest_complete_year": 2025,
            "complete_shared_years": 11,
            "scope": "Synthetic product demonstration only",
        },
        "input_files": {
            name: {"path": f"{name}.csv", "sha256": sha256(output / f"{name}.csv")}
            for name in ("annual_nominal", "fx_daily", "inflation", "references")
        },
        "raw_files": [
            {
                "path": "evidence.txt",
                "sha256": sha256(evidence_path),
                "source_url": "synthetic://repository-authored-demo",
                "retrieved_at": "2026-09-23T00:00:00Z",
                "access_basis": "repository-authored CC0 synthetic values",
                "normalization_recipe": "fixed values written without transformation",
            }
        ],
        "inflation_metadata": {
            currency: {
                "geography": geography,
                "seasonal_adjustment": "not seasonally adjusted",
                "units": "decimal_change",
                "basis": "December-over-December",
            }
            for currency, geography in (("USD", "United States"), ("CNY", "China"))
        },
        "fx_metadata": {
            "quote_orientation": "units_per_USD",
            "observation_timing": "synthetic year-end observation",
            "series": {"CNY": "synthetic", "HKD": "synthetic"},
        },
        "assumptions": [
            LIMITATION,
            "Annual rebalancing; taxes and transaction costs are not modeled",
        ],
    }
    manifest["dataset_id"] = dataset_identity(manifest)
    write_json(output / "manifest.json", manifest)
    write_json(
        output / "portfolio.json",
        {
            "balanced_demo": {"DEMO-GROWTH": 0.6, "DEMO-DEFENSIVE": 0.4},
        },
    )
    (output / "DATA_LICENSE.md").write_text(
        "# Synthetic demonstration data license\n\n"
        "The repository-authored synthetic values in this bundle are dedicated to the public "
        "domain under [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/).\n\n"
        + LIMITATION
        + ". These values must not be represented as historical returns.\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the deterministic, offline synthetic demo bundle")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate_demo_bundle(args.output)
    print("synthetic demo bundle generated")


if __name__ == "__main__":
    main()
