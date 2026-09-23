"""Strict loading and provenance validation for canonical market datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarketDataset:
    manifest: dict
    nominal: pd.DataFrame
    fx_daily: pd.DataFrame
    inflation: pd.DataFrame
    references: pd.DataFrame


def load_strict_json(path: str | Path) -> dict:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"nonfinite JSON constant: {value}")

    result = json.loads(
        Path(path).read_text(encoding="utf-8"),
        object_pairs_hook=object_pairs,
        parse_constant=reject_constant,
    )
    if not isinstance(result, dict):
        raise ValueError("JSON root must be an object")
    return result


def dataset_identity(manifest: dict) -> str:
    content = {key: value for key, value in manifest.items() if key != "dataset_id"}
    try:
        encoded = json.dumps(
            content, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError(f"manifest is not canonical JSON: {error}") from error
    return hashlib.sha256(encoded).hexdigest()


def _require_keys(value: dict, required: set[str], context: str) -> None:
    missing = sorted(required - value.keys())
    if missing:
        raise ValueError(f"{context} missing keys: {', '.join(missing)}")


def _resolve_file(root: Path, entry: dict, context: str) -> Path:
    _require_keys(entry, {"path", "sha256"}, context)
    relative = Path(entry["path"])
    if relative.is_absolute():
        raise ValueError(f"{context} path must be relative: {relative}")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"{context} path escapes manifest directory: {relative}") from error
    if not path.is_file():
        raise ValueError(f"{context} file does not exist: {relative}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != entry["sha256"]:
        raise ValueError(f"{context} checksum mismatch: {relative}")
    return path


def _read_exact_csv(path: Path, columns: list[str], context: str) -> pd.DataFrame:
    table = pd.read_csv(path)
    if table.columns.tolist() != columns:
        raise ValueError(f"{context} has unexpected columns")
    return table


def _integer_years(values: pd.Series, context: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="raise")
    numbers = numeric.to_numpy(dtype=float)
    if not np.isfinite(numbers).all() or not np.equal(numbers, np.floor(numbers)).all():
        raise ValueError(f"{context} requires integer years")
    return numeric.astype(int)


def _finite_numeric(values: pd.Series, context: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="raise")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError(f"{context} must contain finite values")
    return numeric.astype(float)


def _validate_manifest_shape(manifest: dict) -> None:
    _require_keys(
        manifest,
        {
            "schema_version",
            "transformation_version",
            "data_kind",
            "series",
            "coverage",
            "input_files",
            "raw_files",
            "inflation_metadata",
            "fx_metadata",
            "assumptions",
            "dataset_id",
        },
        "manifest",
    )
    if manifest["schema_version"] != 1:
        raise ValueError("unsupported manifest schema_version")
    if manifest["data_kind"] not in {"market", "synthetic_test"}:
        raise ValueError("unrecognized manifest data_kind")
    if not isinstance(manifest["series"], dict) or not manifest["series"]:
        raise ValueError("manifest series must be a nonempty object")
    if manifest["dataset_id"] != dataset_identity(manifest):
        raise ValueError("manifest dataset_id mismatch")


_SERIES_KEYS = {
    "asset_id",
    "series_id",
    "source_id",
    "source_url",
    "methodology_url",
    "listing_market",
    "economic_exposure",
    "asset_family",
    "currency",
    "return_kind",
    "fee_basis",
    "fee_notes",
    "hedge_status",
    "is_proxy",
    "launch_date",
    "backfill_start_date",
    "frequency",
    "annualization_recipe",
    "period_end_convention",
    "first_year",
    "last_year",
    "status",
    "limitations",
}


def _validate_series_metadata(series: dict, nominal: pd.DataFrame) -> None:
    assets_in_data = set(nominal["asset_id"])
    if assets_in_data != set(series):
        raise ValueError("selected assets do not match manifest series metadata")
    for asset_id, metadata in series.items():
        _require_keys(metadata, _SERIES_KEYS, f"series {asset_id}")
        string_fields = {
            "asset_id",
            "series_id",
            "source_id",
            "source_url",
            "methodology_url",
            "listing_market",
            "economic_exposure",
            "asset_family",
            "currency",
            "return_kind",
            "fee_basis",
            "fee_notes",
            "hedge_status",
            "frequency",
            "annualization_recipe",
            "period_end_convention",
            "status",
        }
        for field in string_fields:
            if not isinstance(metadata[field], str):
                raise ValueError(f"series {asset_id} {field} must be a string")
        if metadata["asset_id"] != asset_id:
            raise ValueError(f"series {asset_id} asset_id mismatch")
        if metadata["currency"] not in {"USD", "CNY", "HKD"}:
            raise ValueError(f"series {asset_id} has unrecognized currency")
        if metadata["fee_basis"] not in {
            "gross_of_fund_fees",
            "net_of_fund_fees",
            "source_adjusted",
        }:
            raise ValueError(f"series {asset_id} has unknown fee basis")
        if metadata["fee_basis"] == "source_adjusted" and not metadata["fee_notes"].strip():
            raise ValueError(f"series {asset_id} source_adjusted fee basis requires fee_notes")
        if metadata["status"] != "validated":
            raise ValueError(f"series {asset_id} must be validated before selection")
        if not isinstance(metadata["methodology_url"], str) or not metadata["methodology_url"].strip():
            raise ValueError(f"series {asset_id} requires nonempty methodology")
        if metadata["return_kind"] not in {
            "gross_total_return",
            "net_total_return",
            "source_adjusted_total_return",
            "price_return",
        }:
            raise ValueError(f"series {asset_id} input must be nominal")
        if metadata["asset_family"] in {"equity", "bond", "cash", "reit"} and metadata["return_kind"] == "price_return":
            raise ValueError(f"series {asset_id} is a price-return equity or other income exposure")
        if metadata["frequency"] != "annual":
            raise ValueError(f"series {asset_id} frequency must be annual")
        if not isinstance(metadata["is_proxy"], bool):
            raise ValueError(f"series {asset_id} is_proxy must be boolean")
        if not isinstance(metadata["limitations"], list) or not all(
            isinstance(item, str) for item in metadata["limitations"]
        ):
            raise ValueError(f"series {asset_id} limitations must be a list of strings")
        for field in ["launch_date", "backfill_start_date"]:
            if metadata[field] is not None and not isinstance(metadata[field], str):
                raise ValueError(f"series {asset_id} {field} must be a string or null")
        for field in ["first_year", "last_year"]:
            if not isinstance(metadata[field], int) or isinstance(metadata[field], bool):
                raise ValueError(f"series {asset_id} {field} must be an integer")
        rows = nominal[nominal["asset_id"] == asset_id]
        ids = set(rows["series_id"])
        if len(ids) != 1:
            raise ValueError(f"asset {asset_id} has multiple series IDs")
        if ids != {metadata["series_id"]}:
            raise ValueError(f"asset {asset_id} series_id does not match metadata")
        first, last = int(rows["year"].min()), int(rows["year"].max())
        if metadata["first_year"] != first or metadata["last_year"] != last:
            raise ValueError(f"series {asset_id} date bounds do not match nominal data")


def _validate_inflation_metadata(metadata: dict) -> None:
    expected_geography = {"USD": "United States", "CNY": "China"}
    for currency, geography in expected_geography.items():
        item = metadata.get(currency)
        if not isinstance(item, dict):
            raise ValueError(f"missing {currency} CPI metadata")
        _require_keys(item, {"geography", "seasonal_adjustment", "units", "basis"}, f"{currency} CPI metadata")
        if item["geography"] != geography:
            raise ValueError(f"wrong {currency} CPI geography")
        if item["basis"] != "December-over-December":
            raise ValueError(f"{currency} CPI must use December-over-December basis")
        if item["units"] != "decimal_change":
            raise ValueError(f"{currency} CPI must use decimal_change units")


def load_market_dataset(
    manifest_path: str | Path, *, allow_synthetic: bool = False
) -> MarketDataset:
    manifest_file = Path(manifest_path).resolve()
    manifest = load_strict_json(manifest_file)
    _validate_manifest_shape(manifest)
    if manifest["data_kind"] == "synthetic_test" and not allow_synthetic:
        raise ValueError("synthetic datasets require allow_synthetic=True")

    root = manifest_file.parent
    input_entries = manifest["input_files"]
    required_inputs = {"annual_nominal", "fx_daily", "inflation", "references"}
    if not isinstance(input_entries, dict) or set(input_entries) != required_inputs:
        raise ValueError("input_files must contain the four canonical inputs")
    paths = {
        key: _resolve_file(root, input_entries[key], f"input {key}")
        for key in sorted(required_inputs)
    }

    raw_files = manifest["raw_files"]
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("validated series require raw provenance")
    raw_required = {
        "path",
        "sha256",
        "source_url",
        "retrieved_at",
        "access_basis",
        "normalization_recipe",
    }
    for position, entry in enumerate(raw_files):
        if not isinstance(entry, dict):
            raise ValueError("raw provenance entries must be objects")
        _require_keys(entry, raw_required, f"raw provenance entry {position}")
        _resolve_file(root, entry, f"raw provenance entry {position}")

    nominal = _read_exact_csv(
        paths["annual_nominal"],
        ["year", "asset_id", "series_id", "nominal_return"],
        "annual_nominal",
    )
    nominal["year"] = _integer_years(nominal["year"], "annual_nominal")
    if nominal[["asset_id", "year"]].duplicated().any():
        duplicate = nominal.loc[
            nominal[["asset_id", "year"]].duplicated(keep=False)
        ].iloc[0]
        raise ValueError(f"duplicate asset/year: {duplicate['asset_id']} {duplicate['year']}")
    nominal["nominal_return"] = _finite_numeric(nominal["nominal_return"], "finite return")
    if (nominal["nominal_return"] <= -1).any():
        row = nominal.loc[nominal["nominal_return"] <= -1].iloc[0]
        raise ValueError(f"nominal return must be greater than -1: {row['asset_id']} {row['year']}")
    for asset_id, rows in nominal.groupby("asset_id"):
        if rows["series_id"].nunique() != 1:
            raise ValueError(f"asset {asset_id} has multiple series IDs")
    _validate_series_metadata(manifest["series"], nominal)

    fx = _read_exact_csv(paths["fx_daily"], ["date", "CNY", "HKD"], "fx_daily")
    dates = pd.to_datetime(fx.pop("date"), errors="raise")
    if dates.duplicated().any():
        raise ValueError("duplicate FX dates")
    for currency in ["CNY", "HKD"]:
        fx[currency] = pd.to_numeric(fx[currency], errors="raise")
        present = fx[currency].dropna().to_numpy(dtype=float)
        if not np.isfinite(present).all() or (present <= 0).any():
            raise ValueError(f"FX {currency} observations must be positive and finite")
    fx.index = dates
    fx = fx.sort_index()
    fx.index.name = "date"

    fx_metadata = manifest["fx_metadata"]
    if fx_metadata.get("quote_orientation") != "units_per_USD":
        raise ValueError("FX quote orientation must be units_per_USD")
    if fx_metadata.get("series", {}).get("HKD") != "observed":
        raise ValueError("FX metadata requires observed HKD rates")

    inflation = _read_exact_csv(paths["inflation"], ["year", "USD", "CNY"], "inflation")
    inflation["year"] = _integer_years(inflation["year"], "inflation")
    if inflation["year"].duplicated().any():
        raise ValueError("duplicate inflation year")
    for currency in ["USD", "CNY"]:
        inflation[currency] = _finite_numeric(inflation[currency], f"inflation {currency}")
        if (inflation[currency] <= -1).any():
            raise ValueError(f"inflation {currency} must be greater than -1")
    inflation = inflation.set_index("year").sort_index()
    _validate_inflation_metadata(manifest["inflation_metadata"])

    references = _read_exact_csv(
        paths["references"],
        ["asset_id", "year", "expected_return", "absolute_tolerance", "evidence_path", "evidence_sha256"],
        "references",
    )
    references["year"] = _integer_years(references["year"], "references")
    if references[["asset_id", "year"]].duplicated().any():
        raise ValueError("duplicate reference asset/year")
    references["expected_return"] = _finite_numeric(references["expected_return"], "reference expected return")
    references["absolute_tolerance"] = _finite_numeric(references["absolute_tolerance"], "reference tolerance")
    if (references["absolute_tolerance"] < 0).any():
        raise ValueError("reference tolerance must be nonnegative")
    missing_reference_assets = set(manifest["series"]) - set(references["asset_id"])
    if missing_reference_assets:
        raise ValueError(
            "reference evidence missing for selected assets: "
            + ", ".join(sorted(missing_reference_assets))
        )
    unknown_reference_assets = set(references["asset_id"]) - set(manifest["series"])
    if unknown_reference_assets:
        raise ValueError(
            "reference evidence contains unknown assets: "
            + ", ".join(sorted(unknown_reference_assets))
        )
    if manifest["data_kind"] == "market":
        required_assets = manifest["coverage"].get("required_assets", [])
        if not isinstance(required_assets, list) or not all(
            isinstance(asset, str) for asset in required_assets
        ):
            raise ValueError("coverage required_assets must be a list of strings")
        for asset_id in manifest["series"]:
            count = references.loc[references["asset_id"] == asset_id, "year"].nunique()
            if count < 3:
                raise ValueError(
                    f"at least three non-overlapping reference years required for {asset_id}"
                )
    for row in references.itertuples(index=False):
        try:
            _resolve_file(
                root,
                {"path": row.evidence_path, "sha256": row.evidence_sha256},
                f"reference {row.asset_id} {row.year}",
            )
        except ValueError as error:
            raise ValueError(f"reference evidence checksum/path failure for {row.asset_id} {row.year}: {error}") from error
        asset_rows = nominal[
            (nominal["asset_id"] == row.asset_id) & (nominal["year"] == row.year)
        ]
        if asset_rows.empty:
            raise ValueError(
                f"reference year missing from nominal data: {row.asset_id} {row.year}"
            )
        actual = float(asset_rows.iloc[0]["nominal_return"])
        if abs(actual - row.expected_return) > row.absolute_tolerance:
            raise ValueError(
                f"reference return mismatch for {row.asset_id} {row.year}: "
                f"expected {row.expected_return}, got {actual}"
            )

    wide_nominal = nominal.pivot(index="year", columns="asset_id", values="nominal_return").sort_index()
    wide_nominal.columns.name = None
    return MarketDataset(
        manifest=manifest,
        nominal=wide_nominal,
        fx_daily=fx,
        inflation=inflation,
        references=references,
    )


def _write_canonical_csv(table: pd.DataFrame, path: Path, **kwargs: Any) -> None:
    table.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
        **kwargs,
    )


def build_market_dataset(
    input_manifest: str | Path,
    output_dir: str | Path,
    *,
    as_of: date,
    _allow_synthetic_for_tests: bool = False,
) -> Path:
    """Build and validate a relocatable canonical dataset without network access."""
    input_path = Path(input_manifest).resolve()
    source_root = input_path.parent
    source_manifest = load_strict_json(input_path)
    if source_manifest.get("data_kind") == "synthetic_test" and not _allow_synthetic_for_tests:
        raise ValueError("synthetic datasets cannot be built as production data")
    dataset = load_market_dataset(
        input_path, allow_synthetic=_allow_synthetic_for_tests
    )
    destination = Path(output_dir).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
    try:
        nominal_rows = []
        for year in sorted(dataset.nominal.index):
            for asset_id in sorted(dataset.nominal.columns):
                value = dataset.nominal.at[year, asset_id]
                if pd.notna(value):
                    nominal_rows.append(
                        {
                            "year": int(year),
                            "asset_id": asset_id,
                            "series_id": source_manifest["series"][asset_id]["series_id"],
                            "nominal_return": float(value),
                        }
                    )
        _write_canonical_csv(
            pd.DataFrame(nominal_rows, columns=["year", "asset_id", "series_id", "nominal_return"]),
            staging / "annual_nominal.csv",
        )
        fx = dataset.fx_daily.reset_index().sort_values("date")
        fx["date"] = fx["date"].dt.strftime("%Y-%m-%d")
        _write_canonical_csv(fx[["date", "CNY", "HKD"]], staging / "fx_daily.csv", na_rep="")
        inflation = dataset.inflation.reset_index().sort_values("year")
        _write_canonical_csv(inflation[["year", "USD", "CNY"]], staging / "inflation.csv")

        published: dict[tuple[str, str], str] = {}
        used: dict[tuple[str, str], Path] = {}

        def copy_artifact(relative: str, sha256: str, folder: str) -> str:
            source = (source_root / relative).resolve()
            key = (folder, source.name)
            previous = used.get(key)
            if previous is not None and previous != source:
                raise ValueError(f"duplicate output filename: {folder}/{source.name}")
            used[key] = source
            published[(str(source), folder)] = f"{folder}/{source.name}"
            target = staging / folder / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(source, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
                raise ValueError(f"artifact checksum mismatch: {relative}")
            return target.relative_to(staging).as_posix()

        raw_files = []
        for entry in source_manifest["raw_files"]:
            copied = dict(entry)
            copied["path"] = copy_artifact(entry["path"], entry["sha256"], "raw")
            raw_files.append(copied)

        references = dataset.references.copy().sort_values(["asset_id", "year"])
        evidence_paths = []
        for row in references.itertuples(index=False):
            evidence_paths.append(
                copy_artifact(row.evidence_path, row.evidence_sha256, "evidence")
            )
        references["evidence_path"] = evidence_paths
        _write_canonical_csv(
            references[
                ["asset_id", "year", "expected_return", "absolute_tolerance", "evidence_path", "evidence_sha256"]
            ],
            staging / "references.csv",
        )

        files = {
            "annual_nominal": "annual_nominal.csv",
            "fx_daily": "fx_daily.csv",
            "inflation": "inflation.csv",
            "references": "references.csv",
        }
        input_files = {
            name: {
                "path": relative,
                "sha256": hashlib.sha256((staging / relative).read_bytes()).hexdigest(),
            }
            for name, relative in files.items()
        }
        from pcopt.benchmark import select_common_years

        shared = select_common_years(
            dataset,
            list(dataset.nominal.columns),
            ["USD", "CNY"],
            start_year=None,
            end_year=None,
            as_of=as_of,
        )
        coverage = dict(source_manifest["coverage"])
        coverage.update(
            {
                "first_complete_year": min(shared) if shared else None,
                "latest_complete_year": max(shared) if shared else None,
                "complete_shared_years": len(shared),
            }
        )
        manifest = {
            key: value
            for key, value in source_manifest.items()
            if key not in {"dataset_id", "input_files", "raw_files", "coverage"}
        }
        manifest.update(
            {"coverage": coverage, "input_files": input_files, "raw_files": raw_files}
        )
        manifest["coverage_as_of"] = as_of.isoformat()
        manifest["dataset_id"] = dataset_identity(manifest)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        load_market_dataset(
            staging / "manifest.json", allow_synthetic=_allow_synthetic_for_tests
        )

        if destination.exists():
            existing_files = {
                path.relative_to(destination): path.read_bytes()
                for path in destination.rglob("*")
                if path.is_file()
            }
            staged_files = {
                path.relative_to(staging): path.read_bytes()
                for path in staging.rglob("*")
                if path.is_file()
            }
            if existing_files == staged_files:
                shutil.rmtree(staging)
                return destination / "manifest.json"
            raise FileExistsError(
                f"output directory already contains a different dataset: {destination}; "
                "choose a new output directory"
            )
        os.replace(staging, destination)
        return destination / "manifest.json"
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
