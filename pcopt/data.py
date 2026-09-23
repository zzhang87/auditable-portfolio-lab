from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


def load_returns_csv(path: str | Path) -> pd.DataFrame:
    """Load annual real total returns from CSV.

    Expected format:

    - one row per year;
    - a `year` column or a first unnamed/index column containing years;
    - asset columns with decimal returns, e.g. `0.052` for 5.2%.

    Percent-style strings such as `5.2%` are accepted and converted to `0.052`.
    """

    df = pd.read_csv(path)
    if "year" not in df.columns:
        first = df.columns[0]
        if first.lower().startswith("unnamed") or first.lower() in {"date", "years"}:
            df = df.rename(columns={first: "year"})
        else:
            raise ValueError("returns CSV must include a 'year' column")

    df["year"] = df["year"].astype(int)
    df = df.set_index("year").sort_index()

    for col in df.columns:
        series = df[col]
        if series.dtype == object:
            stripped = series.astype(str).str.strip()
            is_percent = stripped.str.endswith("%")
            numeric = pd.to_numeric(stripped.str.rstrip("%"), errors="coerce")
            numeric = numeric.where(~is_percent, numeric / 100.0)
            df[col] = numeric
        else:
            df[col] = pd.to_numeric(series, errors="coerce")

    return df


def normalize_weights(weights: Mapping[str, float] | Sequence[float], assets: Sequence[str] | None = None) -> pd.Series:
    """Return non-negative weights summing to 1."""

    if isinstance(weights, pd.Series):
        out = weights.astype(float)
    elif isinstance(weights, Mapping):
        out = pd.Series(weights, dtype=float)
    else:
        if assets is None:
            raise ValueError("assets are required when weights are not a mapping")
        out = pd.Series(list(weights), index=list(assets), dtype=float)

    if out.empty:
        raise ValueError("at least one asset weight is required")
    if (out < 0).any():
        raise ValueError("short weights are not supported")

    total = float(out.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("weights must sum to a positive finite number")
    return out / total


def portfolio_returns(
    asset_returns: pd.DataFrame,
    weights: Mapping[str, float] | Sequence[float],
    assets: Sequence[str] | None = None,
    *,
    missing: str = "drop",
) -> pd.Series:
    """Compute annually rebalanced portfolio returns.

    With annual return data and annual rebalancing to target percentages, each
    year's portfolio return is the dot product of that year's asset returns and
    target weights.
    """

    w = normalize_weights(weights, assets)
    missing_assets = [asset for asset in w.index if asset not in asset_returns.columns]
    if missing_assets:
        raise KeyError(f"asset returns missing columns: {missing_assets}")

    subset = asset_returns.loc[:, w.index]
    if missing == "drop":
        subset = subset.dropna(axis=0, how="any")
    elif missing == "raise":
        if subset.isna().any().any():
            raise ValueError("asset returns contain missing values")
    else:
        raise ValueError("missing must be 'drop' or 'raise'")

    return subset.dot(w).rename("portfolio_return")
