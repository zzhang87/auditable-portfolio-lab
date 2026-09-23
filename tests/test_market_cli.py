import copy
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from test_market_data import _synthetic_bundle


def _buildable_bundle(root: Path):
    import hashlib
    from pcopt.market_data import dataset_identity

    input_path, manifest = _synthetic_bundle(root)
    fx = root / "fx_daily.csv"
    fx.write_text(
        "date,CNY,HKD\n2021-12-31,6.80,7.79\n2022-12-30,6.90,7.80\n2023-12-29,7.10,7.81\n"
    )
    manifest["input_files"]["fx_daily"]["sha256"] = hashlib.sha256(fx.read_bytes()).hexdigest()
    manifest["dataset_id"] = dataset_identity(manifest)
    input_path.write_text(json.dumps(manifest))
    return input_path, manifest


def _production_bundle(root: Path) -> Path:
    import hashlib
    from pcopt.market_data import dataset_identity

    input_path, manifest = _buildable_bundle(root)
    nominal = root / "annual_nominal.csv"
    nominal.write_text(
        "year,asset_id,series_id,nominal_return\n"
        "2021,US-EQ,US-EQ-TR,0.02\n2022,US-EQ,US-EQ-TR,0.10\n2023,US-EQ,US-EQ-TR,-0.05\n"
    )
    inflation = root / "inflation.csv"
    inflation.write_text("year,USD,CNY\n2021,0.05,0.01\n2022,0.06,0.02\n2023,0.03,0.01\n")
    evidence_sha = hashlib.sha256((root / "evidence.txt").read_bytes()).hexdigest()
    references = root / "references.csv"
    references.write_text(
        "asset_id,year,expected_return,absolute_tolerance,evidence_path,evidence_sha256\n"
        f"US-EQ,2021,0.02,0.000001,evidence.txt,{evidence_sha}\n"
        f"US-EQ,2022,0.10,0.000001,evidence.txt,{evidence_sha}\n"
        f"US-EQ,2023,-0.05,0.000001,evidence.txt,{evidence_sha}\n"
    )
    for key, path in {"annual_nominal": nominal, "inflation": inflation, "references": references}.items():
        manifest["input_files"][key]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest["data_kind"] = "market"
    manifest["series"]["US-EQ"]["first_year"] = 2021
    manifest["dataset_id"] = dataset_identity(manifest)
    input_path.write_text(json.dumps(manifest))
    return input_path


def test_builder_is_relocatable_and_emits_canonical_bundle(tmp_path):
    from pcopt.market_data import build_market_dataset, load_market_dataset

    source_a = tmp_path / "source-a"
    source_a.mkdir()
    input_a, _ = _buildable_bundle(source_a)
    source_b = tmp_path / "elsewhere" / "source-b"
    shutil.copytree(source_a, source_b)

    built_a = build_market_dataset(input_a, tmp_path / "built-a", as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)
    built_b = build_market_dataset(source_b / "manifest.json", tmp_path / "built-b", as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)

    manifest_a = json.loads(built_a.read_text())
    manifest_b = json.loads(built_b.read_text())
    assert manifest_a == manifest_b
    assert manifest_a["coverage_as_of"] == "2024-06-01"
    assert manifest_a["coverage"]["latest_complete_year"] == 2023
    assert manifest_a["input_files"]["annual_nominal"]["path"] == "annual_nominal.csv"
    assert manifest_a["raw_files"][0]["path"] == "raw/evidence.txt"
    assert load_market_dataset(built_a, allow_synthetic=True).nominal.index.tolist() == [2022, 2023]


def test_failed_build_preserves_existing_output(tmp_path):
    from pcopt.market_data import build_market_dataset

    source = tmp_path / "source"
    source.mkdir()
    input_path, manifest = _buildable_bundle(source)
    output = tmp_path / "built"
    old_manifest = build_market_dataset(input_path, output, as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)
    old_bytes = old_manifest.read_bytes()
    (source / manifest["input_files"]["annual_nominal"]["path"]).write_text("broken\n")

    with pytest.raises(ValueError, match="checksum"):
        build_market_dataset(input_path, output, as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)

    assert (output / "manifest.json").read_bytes() == old_bytes


def test_builder_rejects_duplicate_published_filenames(tmp_path):
    from pcopt.market_data import build_market_dataset, dataset_identity

    source = tmp_path / "source"
    source.mkdir()
    input_path, manifest = _buildable_bundle(source)
    duplicate = source / "other" / "evidence.txt"
    duplicate.parent.mkdir()
    duplicate.write_text("other evidence\n")
    entry = copy.deepcopy(manifest["raw_files"][0])
    entry["path"] = "other/evidence.txt"
    import hashlib
    entry["sha256"] = hashlib.sha256(duplicate.read_bytes()).hexdigest()
    manifest["raw_files"].append(entry)
    manifest["dataset_id"] = dataset_identity(manifest)
    input_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="duplicate output filename"):
        build_market_dataset(input_path, tmp_path / "built", as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)


def test_builder_rejects_synthetic_inputs_by_default(tmp_path):
    from pcopt.market_data import build_market_dataset

    source = tmp_path / "source"
    source.mkdir()
    input_path, _ = _buildable_bundle(source)
    with pytest.raises(ValueError, match="synthetic"):
        build_market_dataset(input_path, tmp_path / "built", as_of=date(2024, 6, 1))


def test_builder_reuses_only_identical_immutable_destination(tmp_path):
    from pcopt.market_data import build_market_dataset

    source = tmp_path / "source"
    source.mkdir()
    input_path, _ = _buildable_bundle(source)
    output = tmp_path / "built"
    first = build_market_dataset(input_path, output, as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)
    first_bytes = first.read_bytes()

    second = build_market_dataset(input_path, output, as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)
    assert second == first
    assert second.read_bytes() == first_bytes

    with pytest.raises(FileExistsError, match="new output directory"):
        build_market_dataset(input_path, output, as_of=date(2025, 6, 1), _allow_synthetic_for_tests=True)
    assert first.read_bytes() == first_bytes


def test_builder_commit_failure_leaves_destination_absent(tmp_path, monkeypatch):
    import pcopt.market_data as market_data

    source = tmp_path / "source"
    source.mkdir()
    input_path, _ = _buildable_bundle(source)
    output = tmp_path / "built"
    monkeypatch.setattr(market_data.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("commit failed")))

    with pytest.raises(OSError, match="commit failed"):
        market_data.build_market_dataset(input_path, output, as_of=date(2024, 6, 1), _allow_synthetic_for_tests=True)
    assert not output.exists()
    assert not list(tmp_path.glob(".built.staging-*"))


def test_builder_cutoff_is_explicit_and_excludes_as_of_year(tmp_path, monkeypatch):
    import pcopt.market_data as market_data

    source = tmp_path / "source"
    source.mkdir()
    input_path, manifest = _buildable_bundle(source)
    nominal = source / manifest["input_files"]["annual_nominal"]["path"]
    nominal.write_text(nominal.read_text() + "2024,US-EQ,US-EQ-TR,0.07\n")
    import hashlib
    manifest["input_files"]["annual_nominal"]["sha256"] = hashlib.sha256(nominal.read_bytes()).hexdigest()
    manifest["series"]["US-EQ"]["last_year"] = 2024
    manifest["dataset_id"] = __import__("pcopt.market_data", fromlist=["dataset_identity"]).dataset_identity(manifest)
    input_path.write_text(json.dumps(manifest))

    class EarlierClock(date):
        @classmethod
        def today(cls):
            return cls(2024, 1, 1)

    class LaterClock(date):
        @classmethod
        def today(cls):
            return cls(2030, 1, 1)

    monkeypatch.setattr(market_data, "date", EarlierClock)
    built = market_data.build_market_dataset(input_path, tmp_path / "built-a", as_of=date(2024, 12, 31), _allow_synthetic_for_tests=True)
    monkeypatch.setattr(market_data, "date", LaterClock)
    rebuilt = market_data.build_market_dataset(input_path, tmp_path / "built-b", as_of=date(2024, 12, 31), _allow_synthetic_for_tests=True)
    result = json.loads(built.read_text())
    assert result["coverage_as_of"] == "2024-12-31"
    assert result["coverage"]["latest_complete_year"] == 2023
    assert built.read_bytes() == rebuilt.read_bytes()


def test_benchmark_parser_and_legacy_commands():
    from pcopt.cli import build_parser, run_benchmark

    parser = build_parser()
    args = parser.parse_args([
        "benchmark", "--manifest", "bundle/manifest.json", "--weights", "weights.json",
        "--base-currency", "both", "--start-year", "2001", "--end-year", "2020",
        "--as-of", "2024-12-31", "--output-dir", "reports",
    ])
    assert args.handler is run_benchmark
    assert (args.manifest, args.weights, args.base_currency) == (
        Path("bundle/manifest.json"), Path("weights.json"), "both"
    )
    assert (args.start_year, args.end_year) == (2001, 2020)
    assert args.as_of == date(2024, 12, 31)
    assert parser.parse_args(["version-roots"]).command == "version-roots"
    assert parser.parse_args([
        "optimize", "--returns", "returns.csv", "--assets", "A,B"
    ]).objective == ["cagr=1"]
    with pytest.raises(SystemExit):
        parser.parse_args(["benchmark", "--base-currency", "EUR"])


def test_cli_report_records_runnable_paths_and_creates_no_database(tmp_path, monkeypatch):
    import pcopt.market_data as market_data
    from pcopt.cli import build_parser, run_benchmark

    source = tmp_path / "source"
    source.mkdir()
    input_path = _production_bundle(source)
    market_data.build_market_dataset(
        input_path, tmp_path / "built", as_of=date(2024, 6, 1)
    )
    weights = tmp_path / "weights.json"
    weights.write_text('{"Only US": {"US-EQ": 1.0}}\n')
    output = tmp_path / "reports"
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args([
        "benchmark", "--manifest", "built/manifest.json", "--weights", "weights.json",
        "--base-currency", "both", "--start-year", "2022", "--end-year", "2023",
        "--output-dir", "reports",
    ])

    report = run_benchmark(args)

    argv = report["reproduce"]["argv"]
    assert argv[0] == "pcopt"
    assert argv[argv.index("--manifest") + 1] == "built/manifest.json"
    assert argv[argv.index("--weights") + 1] == "weights.json"
    assert argv[argv.index("--output-dir") + 1] == "reports"
    assert argv[argv.index("--as-of") + 1] == "2024-06-01"
    assert argv[argv.index("--start-year") + 1] == "2022"
    assert argv[argv.index("--end-year") + 1] == "2023"
    assert (output / "benchmark.json").is_file()
    assert not list(tmp_path.rglob("*.sqlite3"))

    original_cwd = tmp_path
    env = dict(
        os.environ,
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        PATH=f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
    )
    completed = subprocess.run(argv, cwd=original_cwd, env=env, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr


def test_cli_report_redacts_external_manifest_path(tmp_path, monkeypatch):
    import pcopt.market_data as market_data
    from pcopt.cli import build_parser, run_benchmark

    source = tmp_path / "source"
    source.mkdir()
    input_path = _production_bundle(source)
    manifest = market_data.build_market_dataset(
        input_path, tmp_path / "built", as_of=date(2024, 6, 1)
    )
    weights = tmp_path / "weights.json"
    weights.write_text('{"Only US": {"US-EQ": 1.0}}\n')
    invocation_dir = tmp_path / "invocation"
    invocation_dir.mkdir()
    monkeypatch.chdir(invocation_dir)
    args = build_parser().parse_args([
        "benchmark", "--manifest", str(manifest), "--weights", str(weights),
        "--base-currency", "USD", "--output-dir", "reports",
    ])

    report = run_benchmark(args)

    assert report["reproduce"]["runnable"] is False
    assert report["reproduce"]["argv"][3] == "<external>/manifest.json"
    assert str(tmp_path.parent) not in report["reproduce"]["shell_display"]


def test_automatic_boundary_reproduction_is_byte_identical(tmp_path, monkeypatch):
    import pcopt.market_data as market_data
    from pcopt.cli import build_parser, run_benchmark

    source = tmp_path / "source"
    source.mkdir()
    input_path = _production_bundle(source)
    manifest = market_data.build_market_dataset(
        input_path, tmp_path / "built", as_of=date(2024, 6, 1)
    )
    weights = tmp_path / "weights.json"
    weights.write_text('{"Only US": {"US-EQ": 1.0}}\n')
    output = tmp_path / "reports"
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args([
        "benchmark", "--manifest", str(manifest), "--weights", str(weights),
        "--base-currency", "USD", "--output-dir", str(output),
    ])
    report = run_benchmark(args)
    before = {path.name: path.read_bytes() for path in output.iterdir()}

    argv = report["reproduce"]["argv"]
    assert "--start-year" not in argv
    assert "--end-year" not in argv
    env = dict(
        os.environ,
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        PATH=f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
    )
    completed = subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before


def test_cli_requires_explicit_cutoff_for_raw_manifest(tmp_path):
    import pcopt.market_data as market_data
    from pcopt.cli import build_parser, run_benchmark

    source = tmp_path / "source"
    source.mkdir()
    input_path = _production_bundle(source)
    weights = tmp_path / "weights.json"
    weights.write_text('{"Only US": {"US-EQ": 1.0}}\n')
    args = build_parser().parse_args([
        "benchmark", "--manifest", str(input_path), "--weights", str(weights),
        "--base-currency", "USD", "--output-dir", str(tmp_path / "reports"),
    ])
    with pytest.raises(ValueError, match="--as-of.*raw"):
        run_benchmark(args)
