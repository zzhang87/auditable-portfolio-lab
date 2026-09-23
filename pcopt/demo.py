from __future__ import annotations

import hashlib
import json
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


def verify_demo(expected_dir: Path, actual_dir: Path) -> None:
    """Compare report semantics and verify the actual report artifact checksums."""
    for name in ("benchmark.json", "benchmark.md", "benchmark.provenance.json"):
        if not (actual_dir / name).is_file():
            raise AssertionError(f"missing demo artifact: {name}")
    expected = json.loads((expected_dir / "benchmark.json").read_text(encoding="utf-8"))
    actual = json.loads((actual_dir / "benchmark.json").read_text(encoding="utf-8"))
    expected_projection = semantic_projection(expected)
    actual_projection = semantic_projection(actual)
    differing = [
        key for key in SEMANTIC_KEYS
        if expected_projection[key] != actual_projection[key]
    ]
    if differing:
        raise AssertionError("demo semantic mismatch: " + ", ".join(differing))
    provenance = json.loads(
        (actual_dir / "benchmark.provenance.json").read_text(encoding="utf-8")
    )
    for name in ("benchmark.json", "benchmark.md"):
        actual_sha = hashlib.sha256((actual_dir / name).read_bytes()).hexdigest()
        if actual_sha != provenance["artifacts"][name]:
            raise AssertionError(f"demo artifact checksum mismatch: {name}")
