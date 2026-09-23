import copy
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = Path("examples/demo")


def _benchmark_args(output, *, bundle=DEMO, allow=True):
    from pcopt.cli import build_parser

    argv = [
        "benchmark",
        "--manifest",
        str(bundle / "manifest.json"),
        "--weights",
        str(bundle / "portfolio.json"),
        "--base-currency",
        "both",
        "--output-dir",
        str(output),
    ]
    if allow:
        argv.append("--allow-synthetic-demo")
    return build_parser().parse_args(argv)


def test_semantic_projection_detects_provenance_change():
    from pcopt.demo import semantic_projection

    report = {
        "schema_version": 1,
        "dataset_id": "abc",
        "data_kind": "synthetic_test",
        "evaluation": {},
        "source_assumptions": {},
        "provenance": {"fx": {"selected_endpoints": [{"year": 2025}]}},
        "coverage": {},
        "views": {},
        "readiness": {},
        "reproduce": {"shell_display": "machine-specific"},
    }
    changed = copy.deepcopy(report)
    changed["provenance"]["fx"]["selected_endpoints"][0]["year"] = 2024
    assert semantic_projection(report) != semantic_projection(changed)
    changed["provenance"] = report["provenance"]
    changed["reproduce"] = {"shell_display": "portable alternative"}
    assert semantic_projection(report) == semantic_projection(changed)


def test_cli_rejects_synthetic_demo_without_opt_in(tmp_path):
    from pcopt.cli import run_benchmark

    output = tmp_path / "report"
    with pytest.raises(ValueError, match="synthetic"):
        run_benchmark(_benchmark_args(output, allow=False))
    assert not output.exists()


@pytest.mark.parametrize("filename", ["annual_nominal.csv", "evidence.txt"])
def test_tampered_demo_input_fails_before_report_write(tmp_path, filename):
    from pcopt.cli import run_benchmark
    from pcopt.market_data import load_market_dataset

    bundle = tmp_path / "demo"
    shutil.copytree(DEMO, bundle, ignore=shutil.ignore_patterns("expected"))
    with (bundle / filename).open("a", encoding="utf-8") as handle:
        handle.write("2025,DEMO-GROWTH,DEMO-GROWTH-TR,0.99\n")
    with pytest.raises(ValueError, match="checksum"):
        load_market_dataset(bundle / "manifest.json", allow_synthetic=True)
    output = tmp_path / "report"
    with pytest.raises(ValueError, match="checksum"):
        run_benchmark(_benchmark_args(output, bundle=bundle))
    assert not output.exists()


def test_demo_end_to_end_requires_production_data_and_verifies(tmp_path):
    from pcopt.cli import run_benchmark
    from pcopt.demo import verify_demo

    expected = tmp_path / "expected"
    shutil.copytree(DEMO / "expected", expected)
    actual = tmp_path / "actual"
    report = run_benchmark(_benchmark_args(actual))
    assert {path.name for path in actual.iterdir()} == {
        "benchmark.json",
        "benchmark.md",
        "benchmark.provenance.json",
    }
    assert report["data_kind"] == "synthetic_test"
    assert report["readiness"]["production_data_required"] is True
    assert report["readiness"]["status"] == "incomplete"
    assert set(report["views"]) == {"USD", "CNY"}
    assert "--allow-synthetic-demo" in report["reproduce"]["argv"]
    assert "Readiness: **incomplete**" in (actual / "benchmark.md").read_text()
    verify_demo(expected, actual)


@pytest.mark.parametrize(
    "key",
    [
        "schema_version",
        "dataset_id",
        "data_kind",
        "evaluation",
        "source_assumptions",
        "provenance",
        "coverage",
        "views",
        "readiness",
    ],
)
def test_verifier_names_semantic_mismatch(tmp_path, key):
    from pcopt.demo import verify_demo

    actual = tmp_path / "actual"
    shutil.copytree(DEMO / "expected", actual)
    path = actual / "benchmark.json"
    report = json.loads(path.read_text())
    report[key] = "changed"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(AssertionError, match=key):
        verify_demo(DEMO / "expected", actual)


def test_verifier_accepts_last_bit_float_variation(tmp_path):
    from pcopt.demo import verify_demo

    actual = tmp_path / "actual"
    shutil.copytree(DEMO / "expected", actual)
    report_path = actual / "benchmark.json"
    report = json.loads(report_path.read_text())
    returns = report["views"]["CNY"]["portfolios"]["balanced_demo"]["nominal_returns"]
    returns["2015"] = math.nextafter(returns["2015"], math.inf)
    report_path.write_text(json.dumps(report), encoding="utf-8")

    provenance_path = actual / "benchmark.provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["artifacts"]["benchmark.json"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    verify_demo(DEMO / "expected", actual)


@pytest.mark.parametrize("filename", ["benchmark.json", "benchmark.md", "benchmark.provenance.json"])
def test_verifier_names_missing_artifact(tmp_path, filename):
    from pcopt.demo import verify_demo

    actual = tmp_path / "actual"
    shutil.copytree(DEMO / "expected", actual)
    (actual / filename).unlink()
    with pytest.raises(AssertionError, match=filename):
        verify_demo(DEMO / "expected", actual)


@pytest.mark.parametrize("filename", ["benchmark.json", "benchmark.md"])
def test_verifier_rejects_artifact_byte_tampering(tmp_path, filename):
    from pcopt.demo import verify_demo

    actual = tmp_path / "actual"
    shutil.copytree(DEMO / "expected", actual)
    with (actual / filename).open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(AssertionError, match=f"checksum mismatch: {filename}"):
        verify_demo(DEMO / "expected", actual)


def test_generator_reproduces_checked_in_bundle(tmp_path):
    from pcopt.market_data import load_market_dataset

    outputs = [tmp_path / "first", tmp_path / "second"]
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                "scripts/generate_demo_bundle.py",
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    expected = {path.name: path.read_bytes() for path in DEMO.iterdir() if path.is_file()}
    for output in outputs:
        assert {path.name: path.read_bytes() for path in output.iterdir()} == expected
    dataset = load_market_dataset(outputs[0] / "manifest.json", allow_synthetic=True)
    assert dataset.nominal.index.tolist() == list(range(2015, 2026))
    assert dataset.nominal.loc[2015, "DEMO-GROWTH"] == 0.08
    assert dataset.nominal.loc[2025, "DEMO-DEFENSIVE"] == 0.024
    assert dataset.references.groupby("asset_id")["year"].apply(list).to_dict() == {
        "DEMO-GROWTH": [2015, 2020, 2025],
        "DEMO-DEFENSIVE": [2015, 2020, 2025],
    }
