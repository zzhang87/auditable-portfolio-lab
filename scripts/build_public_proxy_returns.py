#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from pcopt.public_data import write_source_catalog, write_us_public_proxy_returns

    parser = argparse.ArgumentParser(description="Build public annual real-return proxy data.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/us_public_proxy_returns.csv"),
        help="Output CSV path for annual real returns.",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("data/public_proxy_sources.json"),
        help="Output JSON path for source provenance.",
    )
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help="Only write source catalog; do not download/build return data.",
    )
    args = parser.parse_args()

    if args.catalog_only:
        write_source_catalog(args.sources)
        print(f"wrote {args.sources}")
        return

    write_us_public_proxy_returns(args.output, args.sources)
    print(f"wrote {args.output}")
    print(f"wrote {args.sources}")


if __name__ == "__main__":
    main()
