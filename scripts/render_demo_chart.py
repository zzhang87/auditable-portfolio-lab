"""Render the checked-in static benchmark overview chart."""

import argparse
from pathlib import Path

from pcopt.visualization import render_benchmark_overview


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="Benchmark JSON report")
    parser.add_argument("--output", type=Path, required=True, help="PNG output path")
    args = parser.parse_args()
    render_benchmark_overview(args.report, args.output)


if __name__ == "__main__":
    main()
