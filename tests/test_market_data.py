import copy
import hashlib
import json
from pathlib import Path

import pytest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(manifest: dict) -> str:
    content = {key: value for key, value in manifest.items() if key != "dataset_id"}
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_manifest(root: Path, manifest: dict) -> Path:
    manifest["dataset_id"] = _identity(manifest)
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, allow_nan=False), encoding="utf-8")
    return path


def _synthetic_bundle(root: Path) -> tuple[Path, dict]:
    nominal = root / "annual_nominal.csv"
    nominal.write_text(
        "year,asset_id,series_id,nominal_return\n2022,US-EQ,US-EQ-TR,0.10\n2023,US-EQ,US-EQ-TR,-0.05\n",
        encoding="utf-8",
    )
    fx = root / "fx_daily.csv"
    fx.write_text(
        "date,CNY,HKD\n2022-12-30,6.90,7.80\n2023-12-29,7.10,7.81\n",
        encoding="utf-8",
    )
    inflation = root / "inflation.csv"
    inflation.write_text("year,USD,CNY\n2022,0.06,0.02\n2023,0.03,0.01\n", encoding="utf-8")
    evidence = root / "evidence.txt"
    evidence.write_text("synthetic reference evidence\n", encoding="utf-8")
    references = root / "references.csv"
    references.write_text(
        "asset_id,year,expected_return,absolute_tolerance,evidence_path,evidence_sha256\n"
        f"US-EQ,2023,-0.05,0.000001,evidence.txt,{_sha(evidence)}\n",
        encoding="utf-8",
    )
    metadata = {
        "asset_id": "US-EQ",
        "series_id": "US-EQ-TR",
        "source_id": "SYNTHETIC",
        "source_url": "https://example.invalid/synthetic",
        "methodology_url": "https://example.invalid/methodology",
        "listing_market": "us",
        "economic_exposure": "Synthetic US equities",
        "asset_family": "equity",
        "currency": "USD",
        "return_kind": "gross_total_return",
        "fee_basis": "gross_of_fund_fees",
        "fee_notes": "Synthetic index return basis",
        "hedge_status": "unhedged",
        "is_proxy": False,
        "launch_date": "2021-01-01",
        "backfill_start_date": None,
        "frequency": "annual",
        "annualization_recipe": "synthetic complete calendar-year returns",
        "period_end_convention": "last valid trading observation at calendar year end",
        "first_year": 2022,
        "last_year": 2023,
        "status": "validated",
        "limitations": ["Synthetic test data only"],
    }
    inputs = {
        name: {"path": path.name, "sha256": _sha(path)}
        for name, path in {
            "annual_nominal": nominal,
            "fx_daily": fx,
            "inflation": inflation,
            "references": references,
        }.items()
    }
    manifest = {
        "schema_version": 1,
        "transformation_version": "test-v1",
        "data_kind": "synthetic_test",
        "series": {"US-EQ": metadata},
        "coverage": {"required_assets": ["US-EQ"], "minimum_shared_years": 2},
        "input_files": inputs,
        "raw_files": [
            {
                "path": "evidence.txt",
                "sha256": _sha(evidence),
                "source_url": "synthetic://evidence",
                "retrieved_at": "2026-09-19T00:00:00Z",
                "access_basis": "generated test fixture",
                "normalization_recipe": "none",
            }
        ],
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
        "fx_metadata": {
            "quote_orientation": "units_per_USD",
            "observation_timing": "New York noon",
            "series": {"CNY": "synthetic", "HKD": "synthetic"},
        },
        "assumptions": ["Synthetic fixture; never publish as market data"],
    }
    return _write_manifest(root, manifest), manifest


def _rewrite_input(root: Path, manifest: dict, key: str, content: str) -> Path:
    path = root / manifest["input_files"][key]["path"]
    path.write_text(content, encoding="utf-8")
    manifest["input_files"][key]["sha256"] = _sha(path)
    return _write_manifest(root, manifest)


def test_load_valid_synthetic_market_dataset(tmp_path):
    from pcopt.market_data import MarketDataset, load_market_dataset

    path, _ = _synthetic_bundle(tmp_path)
    dataset = load_market_dataset(path, allow_synthetic=True)
    assert isinstance(dataset, MarketDataset)
    assert dataset.nominal.columns.tolist() == ["US-EQ"]
    assert dataset.nominal.index.tolist() == [2022, 2023]
    assert dataset.fx_daily.columns.tolist() == ["CNY", "HKD"]
    assert dataset.inflation.columns.tolist() == ["USD", "CNY"]


def test_default_loading_rejects_synthetic_data(tmp_path):
    from pcopt.market_data import load_market_dataset

    path, _ = _synthetic_bundle(tmp_path)
    with pytest.raises(ValueError, match="synthetic"):
        load_market_dataset(path)


def test_synthetic_fx_labels_cannot_be_promoted_to_market(tmp_path):
    from pcopt.market_data import load_market_dataset

    path, manifest = _synthetic_bundle(tmp_path)
    load_market_dataset(path, allow_synthetic=True)
    manifest["data_kind"] = "market"
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="market data requires observed FX"):
        load_market_dataset(path)


def test_loader_detects_changed_file_bytes(tmp_path):
    from pcopt.market_data import load_market_dataset

    path, manifest = _synthetic_bundle(tmp_path)
    (tmp_path / manifest["input_files"]["annual_nominal"]["path"]).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="annual_nominal.*checksum"):
        load_market_dataset(path, allow_synthetic=True)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (
            "year,asset_id,series_id,nominal_return\n2022,US-EQ,US-EQ-TR,0.1\n2022,US-EQ,US-EQ-TR,0.2\n",
            "duplicate asset/year",
        ),
        (
            "year,asset_id,series_id,nominal_return\n2022,US-EQ,US-EQ-TR,0.1\n2023,US-EQ,OTHER,0.2\n",
            "multiple series IDs",
        ),
        (
            "year,asset_id,series_id,nominal_return\n2022.5,US-EQ,US-EQ-TR,0.1\n",
            "integer years",
        ),
        (
            "year,asset_id,series_id,nominal_return\n2022,US-EQ,US-EQ-TR,NaN\n",
            "finite return",
        ),
        (
            "year,asset_id,series_id,nominal_return\n2022,US-EQ,US-EQ-TR,-1.0\n",
            "greater than -1",
        ),
    ],
)
def test_nominal_table_rejects_invalid_rows(tmp_path, content, message):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    path = _rewrite_input(tmp_path, manifest, "annual_nominal", content)
    with pytest.raises(ValueError, match=message):
        load_market_dataset(path, allow_synthetic=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda m: m["series"]["US-EQ"].update(currency="EUR"), "currency"),
        (lambda m: m["series"]["US-EQ"].update(fee_basis="mystery"), "fee basis"),
        (lambda m: m["series"]["US-EQ"].update(status="candidate"), "validated"),
        (lambda m: m["series"]["US-EQ"].update(return_kind="price_return"), "price-return equity"),
        (lambda m: m["series"]["US-EQ"].update(return_kind="real_return"), "nominal"),
        (lambda m: m["series"]["US-EQ"].update(methodology_url=""), "methodology"),
        (lambda m: m["series"]["US-EQ"].update(first_year=2021), "date bounds"),
        (lambda m: m["inflation_metadata"]["USD"].update(geography="China"), "CPI geography"),
        (lambda m: m["inflation_metadata"]["USD"].update(basis="annual average"), "December-over-December"),
        (lambda m: m["fx_metadata"]["series"].update(HKD="fixed"), "synthetic FX series labels"),
        (lambda m: m["fx_metadata"]["series"].update(CNY="observed"), "synthetic FX series labels"),
    ],
)
def test_manifest_rejects_invalid_metadata(tmp_path, mutation, message):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    mutation(manifest)
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match=message):
        load_market_dataset(path, allow_synthetic=True)


def test_source_adjusted_fee_basis_requires_explanation(tmp_path):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    manifest["series"]["US-EQ"].update(
        fee_basis="source_adjusted",
        return_kind="source_adjusted_total_return",
        fee_notes="Historical expense-ratio splice retained from source",
    )
    path = _write_manifest(tmp_path, manifest)
    load_market_dataset(path, allow_synthetic=True)

    manifest["series"]["US-EQ"]["fee_notes"] = ""
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="fee_notes"):
        load_market_dataset(path, allow_synthetic=True)


def test_selected_series_must_use_annual_frequency_and_typed_metadata(tmp_path):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    manifest["series"]["US-EQ"]["frequency"] = "monthly"
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="frequency.*annual"):
        load_market_dataset(path, allow_synthetic=True)

    _, manifest = _synthetic_bundle(tmp_path)
    manifest["series"]["US-EQ"]["is_proxy"] = "false"
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="is_proxy.*boolean"):
        load_market_dataset(path, allow_synthetic=True)


@pytest.mark.parametrize(
    "coverage",
    [
        {},
        {"required_assets": []},
        {"required_assets": ["UNAVAILABLE-CORE"]},
    ],
)
def test_every_selected_production_series_requires_three_reference_years(tmp_path, coverage):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    manifest["data_kind"] = "market"
    manifest["coverage"] = coverage
    manifest["fx_metadata"]["series"] = {"CNY": "observed", "HKD": "observed"}
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="at least three.*US-EQ"):
        load_market_dataset(path)


def test_manifest_requires_raw_provenance_and_reference_evidence(tmp_path):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    manifest["raw_files"] = []
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="raw provenance"):
        load_market_dataset(path, allow_synthetic=True)

    _, manifest = _synthetic_bundle(tmp_path)
    (tmp_path / "evidence.txt").write_text("tampered", encoding="utf-8")
    manifest["raw_files"][0]["sha256"] = _sha(tmp_path / "evidence.txt")
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="reference.*checksum"):
        load_market_dataset(path, allow_synthetic=True)


def test_reference_evidence_must_cover_and_match_selected_assets(tmp_path):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    path = _rewrite_input(
        tmp_path,
        manifest,
        "references",
        "asset_id,year,expected_return,absolute_tolerance,evidence_path,evidence_sha256\n",
    )
    with pytest.raises(ValueError, match="reference evidence.*US-EQ"):
        load_market_dataset(path, allow_synthetic=True)

    _, manifest = _synthetic_bundle(tmp_path)
    evidence_hash = _sha(tmp_path / "evidence.txt")
    path = _rewrite_input(
        tmp_path,
        manifest,
        "references",
        "asset_id,year,expected_return,absolute_tolerance,evidence_path,evidence_sha256\n"
        f"US-EQ,2023,0.90,0.000001,evidence.txt,{evidence_hash}\n",
    )
    with pytest.raises(ValueError, match="reference return mismatch.*US-EQ.*2023"):
        load_market_dataset(path, allow_synthetic=True)


def test_manifest_rejects_unresolved_path(tmp_path):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    manifest["input_files"]["fx_daily"]["path"] = "missing.csv"
    path = _write_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="fx_daily.*does not exist"):
        load_market_dataset(path, allow_synthetic=True)


def test_fx_and_inflation_domains_are_strict(tmp_path):
    from pcopt.market_data import load_market_dataset

    _, manifest = _synthetic_bundle(tmp_path)
    path = _rewrite_input(tmp_path, manifest, "fx_daily", "date,CNY,HKD\n2023-12-29,-1,7.8\n")
    with pytest.raises(ValueError, match="FX.*positive"):
        load_market_dataset(path, allow_synthetic=True)

    _, manifest = _synthetic_bundle(tmp_path)
    path = _rewrite_input(tmp_path, manifest, "inflation", "year,USD,CNY\n2023,-1,0.1\n")
    with pytest.raises(ValueError, match="inflation.*greater than -1"):
        load_market_dataset(path, allow_synthetic=True)


def test_dataset_identity_excludes_only_dataset_id():
    from pcopt.market_data import dataset_identity

    manifest = {"schema_version": 1, "assumptions": ["a"], "dataset_id": "ignored"}
    assert dataset_identity(manifest) == _identity(manifest)
    changed = copy.deepcopy(manifest)
    changed["assumptions"] = ["b"]
    assert dataset_identity(changed) != dataset_identity(manifest)


@pytest.mark.parametrize("text", ['{"a": 1, "a": 2}', '{"a": NaN}', "[1, 2]"])
def test_strict_json_rejects_duplicates_nonfinite_and_nonobject(tmp_path, text):
    from pcopt.market_data import load_strict_json

    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_strict_json(path)
