import math

import pandas as pd

from pcopt import public_data
from pcopt.public_data import (
    build_us_public_proxy_returns,
    parse_freegoldapi_prices,
    parse_french_annual_6_portfolios,
    real_returns,
)


def test_parse_french_annual_6_portfolios_value_weighted_block():
    text = """
header
  Average Value Weighted Returns -- Annual
,SMALL LoBM,ME1 BM2,SMALL HiBM,BIG LoBM,ME2 BM2,BIG HiBM
  2020,  10.0000,   5.0000,  -2.0000,  12.0000,   6.0000,   1.0000
  2021, -99.9900,   7.0000,   3.0000,  11.0000,   5.0000,   2.0000

  Average Equal Weighted Returns -- Annual
"""

    df = parse_french_annual_6_portfolios(text)

    assert list(df.index) == [2020, 2021]
    assert math.isclose(df.loc[2020, "SMALL LoBM"], 0.10)
    assert math.isnan(df.loc[2021, "SMALL LoBM"])
    assert math.isclose(df.loc[2021, "BIG HiBM"], 0.02)


def test_real_returns_aligns_and_deflates_nominal_returns():
    nominal = pd.Series({2020: 0.10, 2021: 0.05}, name="asset")
    inflation = pd.Series({2021: 0.02, 2022: 0.03}, name="inflation")

    out = real_returns(nominal, inflation)

    assert list(out.index) == [2021]
    assert math.isclose(out.loc[2021], (1.05 / 1.02) - 1.0)


def test_parse_freegoldapi_prices_uses_usd_prices_only():
    text = """date,price,source
1959-01-01,35.0,measuringworth_london (GBP)
1960-01-01,35.27,world_bank
1960-12-01,36.50,world_bank
1961-12-01,35.25,world_bank
"""

    out = parse_freegoldapi_prices(text)

    assert list(out.index) == [pd.Timestamp("1960-01-01"), pd.Timestamp("1960-12-01"), pd.Timestamp("1961-12-01")]
    assert math.isclose(out.iloc[1], 36.50)


def test_build_us_public_proxy_returns_includes_developed_ex_us_equity_assets(monkeypatch):
    inflation = pd.Series({2020: 0.02, 2021: 0.03}, name="inflation")
    french_us = pd.DataFrame(
        {
            "SMALL LoBM": [0.10, 0.11],
            "ME1 BM2": [0.12, 0.13],
            "SMALL HiBM": [0.14, 0.15],
            "BIG LoBM": [0.16, 0.17],
            "ME2 BM2": [0.18, 0.19],
            "BIG HiBM": [0.20, 0.21],
        },
        index=[2020, 2021],
    )
    french_xus = pd.DataFrame(
        {
            "SMALL LoBM": [0.30, 0.31],
            "ME1 BM2": [0.32, 0.33],
            "SMALL HiBM": [0.34, 0.35],
            "BIG LoBM": [0.36, 0.37],
            "ME2 BM2": [0.38, 0.39],
            "BIG HiBM": [0.40, 0.41],
        },
        index=[2020, 2021],
    )

    def fake_fetch_french(region: str = "USA") -> pd.DataFrame:
        if region == "USA":
            return french_us
        if region == "XUS":
            return french_xus
        raise AssertionError(f"unexpected region {region}")

    monkeypatch.setattr(public_data, "annual_cpi_inflation", lambda _series: inflation)
    monkeypatch.setattr(public_data, "fetch_fred_series", lambda series_id: pd.Series(dtype=float, name=series_id))
    monkeypatch.setattr(public_data, "fetch_french_annual_6_portfolios", fake_fetch_french)
    monkeypatch.setattr(
        public_data, "treasury_bill_returns_from_discount_yield", lambda _series: pd.Series(dtype=float, name="USA-BIL")
    )
    monkeypatch.setattr(
        public_data, "treasury_duration_returns", lambda _series, duration, label: pd.Series(dtype=float, name=label)
    )
    monkeypatch.setattr(public_data, "combine_yield_series", lambda *series: pd.Series(dtype=float, name="yield"))

    out, _ = build_us_public_proxy_returns(start_year=2020, include_commodities=False)

    for asset in ("XUS-SCG", "XUS-SCB", "XUS-SCV", "XUS-LCG", "XUS-LCB", "XUS-LCV"):
        assert asset in out.columns

    assert math.isclose(out.loc[2020, "XUS-LCG"], (1.36 / 1.02) - 1.0)
    assert math.isclose(out.loc[2021, "XUS-LCV"], (1.41 / 1.03) - 1.0)
