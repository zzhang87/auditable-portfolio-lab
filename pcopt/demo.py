from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SEMANTIC_KEYS = (
    "schema_version",
    "dataset_id",
    "data_kind",
    "evaluation",
    "source_assumptions",
    "provenance",
    "coverage",
    "views",
    "readiness",
)


def semantic_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    """Retain report meaning, including provenance, independently of replay paths."""
    return {key: report[key] for key in SEMANTIC_KEYS}


def _semantic_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(expected), float(actual), rel_tol=1e-12, abs_tol=1e-15)
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        return expected.keys() == actual.keys() and all(_semantic_equal(expected[key], actual[key]) for key in expected)
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            _semantic_equal(expected_item, actual_item)
            for expected_item, actual_item in zip(expected, actual, strict=True)
        )
    return expected == actual


def verify_demo(expected_dir: Path, actual_dir: Path) -> None:
    """Compare report semantics and verify the actual report artifact checksums."""
    for name in ("benchmark.json", "benchmark.md", "benchmark.provenance.json"):
        if not (actual_dir / name).is_file():
            raise AssertionError(f"missing demo artifact: {name}")
    expected = json.loads((expected_dir / "benchmark.json").read_text(encoding="utf-8"))
    actual = json.loads((actual_dir / "benchmark.json").read_text(encoding="utf-8"))
    expected_projection = semantic_projection(expected)
    actual_projection = semantic_projection(actual)
    differing = [key for key in SEMANTIC_KEYS if not _semantic_equal(expected_projection[key], actual_projection[key])]
    if differing:
        raise AssertionError("demo semantic mismatch: " + ", ".join(differing))
    provenance = json.loads((actual_dir / "benchmark.provenance.json").read_text(encoding="utf-8"))
    for name in ("benchmark.json", "benchmark.md"):
        actual_sha = hashlib.sha256((actual_dir / name).read_bytes()).hexdigest()
        if actual_sha != provenance["artifacts"][name]:
            raise AssertionError(f"demo artifact checksum mismatch: {name}")
