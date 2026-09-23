"""Parsing for cached FRED CSV exports."""

from pathlib import Path

import pandas as pd


def parse_fred_csv(path: str | Path, series_id: str) -> pd.Series:
    """Parse a two-column FRED export without filling missing observations."""
    table = pd.read_csv(path, na_values=["."])
    if table.columns.tolist() != ["observation_date", series_id]:
        raise ValueError("unexpected FRED columns")
    dates = pd.to_datetime(table["observation_date"], errors="raise")
    if dates.duplicated().any():
        raise ValueError("duplicate FRED dates")
    values = pd.to_numeric(table[series_id], errors="raise")
    return pd.Series(values.to_numpy(), index=dates, name=series_id).sort_index()
