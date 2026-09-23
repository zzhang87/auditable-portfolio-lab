#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from pcopt.simba import write_simba_proxy_returns

    parser = argparse.ArgumentParser(description="Build Portfolio Charts-style proxy data from Simba workbook.")
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("data/Backtest-Portfolio-returns-rev25c.xlsx"),
        help="Path to Simba's Backtesting Spreadsheet workbook.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/simba_proxy_returns.csv"),
        help="Output CSV path for annual real returns.",
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        default=Path("data/simba_proxy_coverage.json"),
        help="Output JSON path for mapping coverage and limitations.",
    )
    parser.add_argument(
        "--assets",
        help="Optional comma-separated Portfolio Charts-style asset codes to emit.",
    )
    args = parser.parse_args()

    asset_codes = None
    if args.assets:
        asset_codes = [item.strip() for item in args.assets.split(",") if item.strip()]

    write_simba_proxy_returns(
        args.workbook,
        args.output,
        args.coverage,
        asset_codes=asset_codes,
    )
    print(f"wrote {args.output}")
    print(f"wrote {args.coverage}")


if __name__ == "__main__":
    main()
