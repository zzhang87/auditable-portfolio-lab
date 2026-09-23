from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import requests

FRENCH_BASE_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
FREEGOLDAPI_CSV_URL = "https://freegoldapi.com/data/latest.csv"


@dataclass(frozen=True)
class SourceInfo:
    asset: str
    source: str
    url: str
    method: str
    limitations: str


FRENCH_6_PORTFOLIO_FILES: dict[str, str] = {
    "USA": "6_Portfolios_2x3_CSV.zip",
    "DEV": "Developed_6_Portfolios_ME_BE-ME_CSV.zip",
    "XUS": "Developed_ex_US_6_Portfolios_ME_BE-ME_CSV.zip",
    "EUR": "Europe_6_Portfolios_ME_BE-ME_CSV.zip",
    "JPN": "Japan_6_Portfolios_ME_BE-ME_CSV.zip",
    "NAM": "North_America_6_Portfolios_ME_BE-ME_CSV.zip",
    "APA": "Asia_Pacific_ex_Japan_6_Portfolios_ME_BE-ME_CSV.zip",
    "EMT": "Emerging_Markets_6_Portfolios_ME_BE-ME_CSV.zip",
}


def source_catalog() -> list[SourceInfo]:
    """Public source map for Portfolio Charts-like assets.

    The automated builder currently targets the U.S. proxy set. Other regions
    are included in the catalog where a public index family exists.
    """

    rows = [
        SourceInfo(
            asset="USA-LCB/LCV/LCG/SCB/SCV/SCG",
            source="Kenneth R. French Data Library, 6 Portfolios Formed on Size and Book-to-Market",
            url=f"{FRENCH_BASE_URL}/6_Portfolios_2x3_CSV.zip",
            method=(
                "Annual value-weighted returns; big and small book-to-market portfolios are mapped "
                "to large/small growth, blend, and value proxies."
            ),
            limitations="U.S. CRSP research portfolios, not investable fund indexes; nominal total returns.",
        ),
        SourceInfo(
            asset="DEV/XUS/EUR/JPN/NAM/APA/EMT equity style proxies",
            source="Kenneth R. French Data Library international 6 size/book-to-market portfolios",
            url="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
            method="Same style mapping as U.S. where annual value-weighted returns are available.",
            limitations="USD research returns for most regional files; not local-currency Portfolio Charts data.",
        ),
        SourceInfo(
            asset="USA-BIL",
            source="FRED TB3MS, 3-Month Treasury Bill Secondary Market Rate",
            url=FRED_CSV_URL.format(series_id="TB3MS"),
            method="Annual nominal return approximated from average annual discount yield.",
            limitations="Yield-based approximation, not a bill index total return.",
        ),
        SourceInfo(
            asset="USA-STT/ITT/LTT",
            source="FRED Treasury yields GS1/GS10/GS20/LTGOVTBD",
            url="https://fred.stlouisfed.org/categories/115",
            method="Annual nominal total return approximated from yield income and duration price effect.",
            limitations="Transparent duration approximation, not a full Treasury index replication.",
        ),
        SourceInfo(
            asset="GLO-COM",
            source="FRED PALLFNFINDEXM, IMF Global Price Index of All Commodities",
            url=FRED_CSV_URL.format(series_id="PALLFNFINDEXM"),
            method="Annual calendar-year price return from monthly index values.",
            limitations="Spot/price index proxy; not collateralized commodity futures total return.",
        ),
        SourceInfo(
            asset="GLO-GLD",
            source="FreeGoldAPI USD-normalized gold prices",
            url=FREEGOLDAPI_CSV_URL,
            method="Annual calendar-year price return from USD gold price observations.",
            limitations=(
                "Third-party public aggregate. The post-1960 history cites World Bank Pink Sheet prices, "
                "and recent values may use gold futures rather than LBMA fixings."
            ),
        ),
        SourceInfo(
            asset="USA-REI",
            source="FTSE Nareit All Equity REITs / Nareit REITWatch",
            url="https://www.reit.com/data-research/reit-indexes",
            method="Manual import recommended from Nareit/FTSE published tables or licensed index data.",
            limitations="Current freely accessible material is often PDF/factsheet format, not a stable CSV API.",
        ),
        SourceInfo(
            asset="Inflation deflator",
            source="FRED CPIAUCSL, Consumer Price Index for All Urban Consumers",
            url=FRED_CSV_URL.format(series_id="CPIAUCSL"),
            method="Calendar-year CPI inflation from December-over-December CPI.",
            limitations="U.S. CPI only; use local CPI for non-U.S. real returns.",
        ),
    ]
    return rows


def write_source_catalog(path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([asdict(row) for row in source_catalog()], indent=2), encoding="utf-8")


def fetch_french_annual_6_portfolios(region: str = "USA") -> pd.DataFrame:
    """Download annual value-weighted 2x3 size/book-to-market returns.

    Returns are decimal nominal total returns indexed by year.
    """

    region_key = region.upper()
    if region_key not in FRENCH_6_PORTFOLIO_FILES:
        raise KeyError(f"unsupported French 6-portfolio region: {region!r}")

    url = f"{FRENCH_BASE_URL}/{FRENCH_6_PORTFOLIO_FILES[region_key]}"
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"no CSV found in {url}")
        text = zf.read(csv_names[0]).decode("utf-8", errors="replace")

    return parse_french_annual_6_portfolios(text)


def parse_french_annual_6_portfolios(text: str) -> pd.DataFrame:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if "Average Value Weighted Returns -- Annual" in line:
            start = idx + 1
            break
    if start is None:
        raise ValueError("could not find annual value-weighted returns block")

    block: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            if block:
                break
            continue
        block.append(line)

    reader = csv.reader(block)
    rows = list(reader)
    if len(rows) < 2:
        raise ValueError("annual returns block is empty")

    header = ["year", *[col.strip() for col in rows[0][1:]]]
    records = []
    for row in rows[1:]:
        if not row or not row[0].strip().isdigit():
            continue
        values = [row[0].strip(), *[item.strip() for item in row[1:]]]
        records.append(values)

    df = pd.DataFrame(records, columns=header)
    df["year"] = df["year"].astype(int)
    for col in df.columns[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0
        df[col] = df[col].where(df[col] > -0.99)
    return df.set_index("year").sort_index()


def fetch_fred_series(series_id: str) -> pd.Series:
    url = FRED_CSV_URL.format(series_id=series_id)
    df = pd.read_csv(url, na_values=["."])
    if df.shape[1] != 2:
        raise ValueError(f"unexpected FRED CSV shape for {series_id}: {df.shape}")
    date_col, value_col = df.columns
    series = pd.Series(pd.to_numeric(df[value_col], errors="coerce").to_numpy(), index=pd.to_datetime(df[date_col]))
    series.name = series_id
    return series.dropna()


def fetch_freegoldapi_prices() -> pd.Series:
    response = requests.get(FREEGOLDAPI_CSV_URL, timeout=60)
    response.raise_for_status()
    return parse_freegoldapi_prices(response.text)


def parse_freegoldapi_prices(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    required = {"date", "price", "source"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"FreeGoldAPI CSV missing column(s): {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["date", "price", "source"])
    usd_mask = ~df["source"].astype(str).str.contains(r"\(GBP\)", case=False, regex=True)
    series = pd.Series(df.loc[usd_mask, "price"].to_numpy(), index=df.loc[usd_mask, "date"])
    series = series.sort_index()
    series.name = "GLO-GLD"
    return series


def annual_price_returns(series: pd.Series) -> pd.Series:
    """Calendar-year returns from last available observation in each year."""

    annual = series.dropna().resample("YE").last()
    out = annual.pct_change().dropna()
    out.index = out.index.year
    return out


def annual_cpi_inflation(series: pd.Series) -> pd.Series:
    return annual_price_returns(series).rename("inflation")


def real_returns(nominal_returns: pd.Series, inflation: pd.Series) -> pd.Series:
    aligned = pd.concat([nominal_returns, inflation], axis=1, join="inner").dropna()
    if aligned.shape[1] != 2:
        raise ValueError("expected exactly two aligned return series")
    out = (1.0 + aligned.iloc[:, 0]) / (1.0 + aligned.iloc[:, 1]) - 1.0
    out.name = nominal_returns.name
    return out


def treasury_bill_returns_from_discount_yield(discount_yield: pd.Series) -> pd.Series:
    """Approximate annual T-bill return from average quoted discount yield."""

    avg_yield = discount_yield.resample("YE").mean() / 100.0
    out = avg_yield.dropna()
    out.index = out.index.year
    out.name = "USA-BIL"
    return out


def treasury_duration_returns(yield_series: pd.Series, duration: float, label: str) -> pd.Series:
    """Approximate Treasury annual total return from yield and duration.

    Formula: prior-year yield income minus modified duration times the annual
    yield change. This is intentionally simple and transparent.
    """

    annual_yield = yield_series.resample("YE").last() / 100.0
    y0 = annual_yield.shift(1)
    dy = annual_yield - annual_yield.shift(1)
    out = (y0 - duration * dy).dropna()
    out.index = out.index.year
    out.name = label
    return out


def combine_yield_series(*series: pd.Series) -> pd.Series:
    if not series:
        raise ValueError("at least one yield series is required")
    out = series[0].copy()
    for fallback in series[1:]:
        out = out.combine_first(fallback)
    return out.sort_index()


def map_french_equity_assets(french_returns: pd.DataFrame, prefix: str) -> pd.DataFrame:
    mapping = {
        f"{prefix}-SCG": "SMALL LoBM",
        f"{prefix}-SCB": "ME1 BM2",
        f"{prefix}-SCV": "SMALL HiBM",
        f"{prefix}-LCG": "BIG LoBM",
        f"{prefix}-LCB": "ME2 BM2",
        f"{prefix}-LCV": "BIG HiBM",
    }
    missing = [source for source in mapping.values() if source not in french_returns.columns]
    if missing:
        raise KeyError(f"missing French source columns: {missing}")
    return pd.DataFrame({asset: french_returns[source] for asset, source in mapping.items()})


def build_us_public_proxy_returns(
    *,
    start_year: int = 1970,
    include_commodities: bool = True,
) -> tuple[pd.DataFrame, list[SourceInfo]]:
    """Build a U.S. annual real-return proxy set from public data.

    The output is meant as a practical public substitute, not a reproduction of
    Portfolio Charts' proprietary composite histories.
    """

    inflation = annual_cpi_inflation(fetch_fred_series("CPIAUCSL"))
    us_french = map_french_equity_assets(fetch_french_annual_6_portfolios("USA"), "USA")
    xus_french = map_french_equity_assets(fetch_french_annual_6_portfolios("XUS"), "XUS")

    nominal: dict[str, pd.Series] = {}
    for equity_block in (us_french, xus_french):
        for col in equity_block.columns:
            nominal[col] = equity_block[col].rename(col)

    nominal["USA-BIL"] = treasury_bill_returns_from_discount_yield(fetch_fred_series("TB3MS"))
    nominal["USA-STT"] = treasury_duration_returns(fetch_fred_series("GS1"), duration=0.9, label="USA-STT")
    nominal["USA-ITT"] = treasury_duration_returns(fetch_fred_series("GS10"), duration=7.5, label="USA-ITT")
    ltt_yield = combine_yield_series(
        fetch_fred_series("GS20"), fetch_fred_series("LTGOVTBD"), fetch_fred_series("GS10")
    )
    nominal["USA-LTT"] = treasury_duration_returns(ltt_yield, duration=14.0, label="USA-LTT")

    if include_commodities:
        nominal["GLO-COM"] = annual_price_returns(fetch_fred_series("PALLFNFINDEXM")).rename("GLO-COM")
        nominal["GLO-GLD"] = annual_price_returns(fetch_freegoldapi_prices()).rename("GLO-GLD")

    real = {asset: real_returns(series, inflation).rename(asset) for asset, series in nominal.items()}
    df = pd.DataFrame(real).sort_index()
    df = df.loc[df.index >= start_year]
    last_completed_year = date.today().year - 1
    last_french_year = min(int(us_french.index.max()), int(xus_french.index.max()))
    df = df.loc[df.index <= min(last_completed_year, last_french_year)]
    return df, source_catalog()


def write_us_public_proxy_returns(output_csv: str | Path, source_json: str | Path | None = None) -> None:
    df, sources = build_us_public_proxy_returns()
    out = Path(output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index(names="year").to_csv(out, index=False)
    if source_json is not None:
        source_out = Path(source_json)
        source_out.parent.mkdir(parents=True, exist_ok=True)
        source_out.write_text(json.dumps([asdict(row) for row in sources], indent=2), encoding="utf-8")
