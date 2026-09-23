#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests


BASE_URL = "https://portfoliocharts.com"
PAGES = {
    "methodology": f"{BASE_URL}/user-guide/methodology/",
    "data_sources": f"{BASE_URL}/user-guide/data-sources/",
    "annual_returns": f"{BASE_URL}/charts/annual-returns/",
    "optimizer": f"{BASE_URL}/charts/optimizer/",
}

ASSET_RE = re.compile(r'data-asset="([^"]+)"[^>]*aria-label="([^"]+)"')
LINK_RE = re.compile(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean_text(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value)
    return SPACE_RE.sub(" ", value).strip()


def fetch(url: str) -> str:
    response = requests.get(url, timeout=30, headers={"User-Agent": "pcopt research metadata collector"})
    response.raise_for_status()
    return response.text


def collect() -> dict[str, object]:
    pages = {name: fetch(url) for name, url in PAGES.items()}

    assets: dict[str, str] = {}
    for page_name in ("annual_returns", "optimizer"):
        for code, label in ASSET_RE.findall(pages[page_name]):
            assets[html.unescape(code)] = html.unescape(label)

    source_links = []
    for href, label in LINK_RE.findall(pages["data_sources"]):
        text = clean_text(label)
        if not text:
            continue
        source_links.append({"label": text, "url": urljoin(PAGES["data_sources"], html.unescape(href))})

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "site": BASE_URL,
        "pages": PAGES,
        "important_limit": (
            "Portfolio Charts states on its Data Sources page that raw data is not redistributed "
            "and online tools are designed to prevent scraping of the original numbers. This "
            "collector therefore stores public methodology, source links, and asset taxonomy only."
        ),
        "methodology_summary": [
            "Year-end returns as of December 31.",
            "Total returns include reinvested dividends and interest.",
            "Portfolios are rebalanced annually to target percentages.",
            "Returns are real returns adjusted for local CPI inflation.",
            "Returns are expressed in each investor's local currency.",
            "Contribution and withdrawal calculators use constant real cash flows.",
            "Taxes and expense ratios are excluded.",
        ],
        "asset_taxonomy": [{"code": code, "label": label} for code, label in sorted(assets.items())],
        "public_source_links": source_links,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public Portfolio Charts methodology/source metadata.")
    parser.add_argument("--output", type=Path, default=Path("data/portfoliocharts_public_metadata.json"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(collect(), indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
