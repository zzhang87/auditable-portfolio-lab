"""Pure annual currency conversion and inflation adjustment helpers."""

from collections.abc import Mapping, Sequence
from numbers import Real

import numpy as np
import pandas as pd


def annual_fx_endpoints(fx_daily: pd.DataFrame, years: Sequence[int]) -> pd.DataFrame:
    """Select year-end common CNY/HKD observations within seven calendar days."""
    if not fx_daily.index.is_unique:
        raise ValueError("duplicate FX dates")
    try:
        quotes = fx_daily.loc[:, ["CNY", "HKD"]].copy()
    except KeyError as exc:
        raise ValueError("FX data must contain CNY and HKD quotes") from exc
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in quotes.dtypes):
        raise ValueError("FX observations must be numeric")
    try:
        dates = pd.DatetimeIndex(quotes.index)
    except (TypeError, ValueError) as exc:
        raise ValueError("FX dates must be valid dates") from exc
    if dates.isna().any():
        raise ValueError("FX dates must be valid dates")
    if not dates.is_unique:
        raise ValueError("duplicate FX dates")
    quotes.index = dates
    quotes = quotes.sort_index()
    observed = quotes.stack().dropna().to_numpy(dtype=float)
    if not np.isfinite(observed).all() or (observed <= 0).any():
        raise ValueError("FX observations must be positive and finite")
    common = quotes.dropna(how="any")
    rows = []
    for year in years:
        try:
            endpoint_year = int(year)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"invalid FX endpoint year: {year}") from exc
        if isinstance(year, bool) or endpoint_year != year:
            raise ValueError(f"invalid FX endpoint year: {year}")
        boundary = pd.Timestamp(year=endpoint_year, month=12, day=31)
        candidates = common.loc[(common.index <= boundary) & (common.index >= boundary - pd.Timedelta(days=7))]
        if candidates.empty:
            raise ValueError(f"missing common FX endpoint for {endpoint_year}")
        row = candidates.iloc[-1]
        rows.append(
            {
                "year": endpoint_year,
                "USD": 1.0,
                "CNY": float(row["CNY"]),
                "HKD": float(row["HKD"]),
                "observed_date": candidates.index[-1].date().isoformat(),
            }
        )
    result = pd.DataFrame(rows, columns=["year", "USD", "CNY", "HKD", "observed_date"])
    return result.set_index("year")


def convert_nominal_returns(
    nominal: pd.DataFrame,
    currencies: Mapping[str, str],
    fx_endpoints: pd.DataFrame,
    base_currency: str,
) -> pd.DataFrame:
    """Convert calendar-year local-currency returns into ``base_currency``."""
    if base_currency not in {"USD", "CNY"}:
        raise ValueError("base currency must be USD or CNY")
    if not nominal.index.is_unique:
        raise ValueError("duplicate return years")
    if not fx_endpoints.index.is_unique:
        raise ValueError("duplicate FX years")
    out = pd.DataFrame(index=nominal.index)
    for asset in nominal.columns:
        if asset not in currencies:
            raise ValueError(f"missing currency mapping for {asset}")
        local = currencies[asset]
        if local not in {"USD", "CNY", "HKD"}:
            raise ValueError(f"unsupported currency for {asset}")
        values = []
        for year, ret in nominal[asset].items():
            try:
                current = int(year)
                numeric_return = float(ret)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"invalid nominal observation: {asset}/{year}") from exc
            if isinstance(year, bool) or current != year or not np.isfinite(numeric_return) or numeric_return <= -1:
                raise ValueError(f"invalid nominal observation: {asset}/{year}")
            previous = current - 1
            try:
                quotes = fx_endpoints.loc[[previous, current], [base_currency, local]]
            except KeyError as exc:
                raise ValueError(f"missing FX endpoint: {asset}/{year}") from exc
            if not all(
                isinstance(value, Real) and not isinstance(value, (bool, np.bool_)) for value in quotes.to_numpy().flat
            ):
                raise ValueError(f"invalid FX endpoint: {asset}/{year}")
            try:
                quote_values = quotes.to_numpy(dtype=float)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid FX endpoint: {asset}/{year}") from exc
            if not np.isfinite(quote_values).all() or (quote_values <= 0).any():
                raise ValueError(f"invalid FX endpoint: {asset}/{year}")
            f0 = quote_values[0, 0] / quote_values[0, 1]
            f1 = quote_values[1, 0] / quote_values[1, 1]
            values.append((1.0 + numeric_return) * float(f1 / f0) - 1.0)
        out[asset] = values
    return out


def deflate_returns(nominal_in_base: pd.DataFrame, inflation: pd.Series) -> pd.DataFrame:
    """Convert nominal returns to purchasing-power returns by calendar year."""
    if not inflation.index.is_unique:
        raise ValueError("duplicate inflation years")
    aligned = inflation.reindex(nominal_in_base.index)
    try:
        inflation_values = aligned.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("missing or invalid inflation") from exc
    if not np.isfinite(inflation_values).all() or (inflation_values <= -1).any():
        raise ValueError("missing or invalid inflation")
    try:
        values = nominal_in_base.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid nominal returns") from exc
    if not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("invalid nominal returns")
    return (nominal_in_base + 1.0).div(aligned + 1.0, axis=0) - 1.0
