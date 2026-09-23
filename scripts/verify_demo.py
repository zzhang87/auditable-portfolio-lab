from __future__ import annotations

import argparse
from pathlib import Path

from pcopt.demo import verify_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify offline demo report semantics and checksums")
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--actual", required=True, type=Path)
    args = parser.parse_args()
    verify_demo(args.expected, args.actual)
    print("demo verification passed")


if __name__ == "__main__":
    main()
