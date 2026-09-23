from __future__ import annotations

import argparse
import shlex
from pathlib import Path


def display_path(value: Path, cwd: Path) -> tuple[str, bool]:
    if not value.is_absolute():
        return value.as_posix(), True
    try:
        return value.resolve().relative_to(cwd.resolve()).as_posix(), True
    except ValueError:
        return f"<external>/{value.name}", False


def build_replay(
    args: argparse.Namespace,
    as_of: str,
    cwd: Path,
) -> dict[str, object]:
    manifest, manifest_ok = display_path(args.manifest, cwd)
    weights, weights_ok = display_path(args.weights, cwd)
    output, output_ok = display_path(args.output_dir, cwd)
    argv = [
        "pcopt",
        "benchmark",
        "--manifest",
        manifest,
        "--weights",
        weights,
        "--base-currency",
        args.base_currency,
        "--output-dir",
        output,
        "--as-of",
        as_of,
    ]
    if args.start_year is not None:
        argv.extend(["--start-year", str(args.start_year)])
    if args.end_year is not None:
        argv.extend(["--end-year", str(args.end_year)])
    if getattr(args, "allow_synthetic_demo", False):
        argv.append("--allow-synthetic-demo")
    return {
        "argv": argv,
        "shell_display": shlex.join(argv),
        "runnable": manifest_ok and weights_ok and output_ok,
        "cwd_policy": "run from the repository root",
    }
