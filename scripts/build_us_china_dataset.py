#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pcopt.market_data import build_market_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a qualified market dataset offline")
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--as-of",
        required=True,
        type=date.fromisoformat,
        help="Explicit completeness cutoff (YYYY-MM-DD); its calendar year is excluded",
    )
    args = parser.parse_args()
    manifest_path = build_market_dataset(args.inputs, args.output_dir, as_of=args.as_of)
    print(manifest_path)


if __name__ == "__main__":
    main()
