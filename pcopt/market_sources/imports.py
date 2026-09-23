"""Deterministic transformations for imported market levels."""

from datetime import date

import numpy as np
import pandas as pd


def annual_returns_from_levels(levels: pd.Series, *, as_of: date) -> pd.DataFrame:
    """Build decimal annual returns from verified calendar-year-end levels."""
    if not isinstance(levels.index, pd.DatetimeIndex):
        raise ValueError("levels index must contain dates")
    if levels.index.duplicated().any():
        raise ValueError("duplicate level dates")
    numeric = pd.to_numeric(levels, errors="raise")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("levels must be finite")
    if (values <= 0).any():
        raise ValueError("levels must be positive")

    completed = numeric[numeric.index.year < as_of.year].sort_index()
    endpoints = completed.groupby(completed.index.year).tail(1)
    if endpoints.empty:
        return pd.DataFrame(
            columns=["nominal_return", "start_observed_date", "end_observed_date"]
        ).rename_axis("year")

    years = endpoints.index.year.to_numpy()
    if len(years) > 1 and not np.all(np.diff(years) == 1):
        raise ValueError("level endpoints must cover consecutive calendar years")
    for timestamp in endpoints.index:
        days_before_end = (pd.Timestamp(timestamp.year, 12, 31) - timestamp.normalize()).days
        if days_before_end < 0 or days_before_end > 7:
            raise ValueError(f"year {timestamp.year} endpoint violates seven-day rule")

    records = []
    endpoint_values = endpoints.to_numpy(dtype=float)
    for position in range(1, len(endpoints)):
        records.append(
            {
                "year": int(years[position]),
                "nominal_return": endpoint_values[position] / endpoint_values[position - 1] - 1.0,
                "start_observed_date": endpoints.index[position - 1].date(),
                "end_observed_date": endpoints.index[position].date(),
            }
        )
    return pd.DataFrame.from_records(records).set_index("year") if records else pd.DataFrame(
        columns=["nominal_return", "start_observed_date", "end_observed_date"],
        index=pd.Index([], name="year"),
    )
