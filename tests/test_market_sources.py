from datetime import date

import pandas as pd
import pytest


def test_consecutive_calendar_year_levels_only():
    from pcopt.market_sources.imports import annual_returns_from_levels

    levels = pd.Series(
        [100.0, 110.0, 121.0],
        index=pd.to_datetime(["2022-12-30", "2023-12-29", "2024-12-31"]),
    )
    result = annual_returns_from_levels(levels, as_of=date(2025, 2, 1))
    assert result.index.tolist() == [2023, 2024]
    assert result["nominal_return"].tolist() == pytest.approx([0.1, 0.1])
    with pytest.raises(ValueError, match="consecutive"):
        annual_returns_from_levels(
            levels.drop(pd.Timestamp("2023-12-29")), as_of=date(2025, 2, 1)
        )


@pytest.mark.parametrize(
    ("levels", "message"),
    [
        (pd.Series([1.0, 2.0], index=pd.to_datetime(["2023-12-29"] * 2)), "duplicate"),
        (pd.Series([1.0, 0.0], index=pd.to_datetime(["2022-12-30", "2023-12-29"])), "positive"),
        (pd.Series([1.0, float("inf")], index=pd.to_datetime(["2022-12-30", "2023-12-29"])), "finite"),
        (pd.Series([1.0, 2.0], index=pd.to_datetime(["2022-12-23", "2023-12-29"])), "seven-day"),
    ],
)
def test_level_import_rejects_invalid_inputs(levels, message):
    from pcopt.market_sources.imports import annual_returns_from_levels

    with pytest.raises(ValueError, match=message):
        annual_returns_from_levels(levels, as_of=date(2024, 2, 1))


def test_level_import_ignores_current_incomplete_year():
    from pcopt.market_sources.imports import annual_returns_from_levels

    levels = pd.Series(
        [100.0, 110.0, 999.0],
        index=pd.to_datetime(["2022-12-30", "2023-12-29", "2024-06-30"]),
    )
    result = annual_returns_from_levels(levels, as_of=date(2024, 7, 1))
    assert result.index.tolist() == [2023]


def test_level_import_returns_decimal_units():
    from pcopt.market_sources.imports import annual_returns_from_levels

    levels = pd.Series(
        [100.0, 105.0], index=pd.to_datetime(["2022-12-30", "2023-12-29"])
    )
    assert annual_returns_from_levels(levels, as_of=date(2024, 1, 2)).iloc[0, 0] == pytest.approx(0.05)


def test_parse_fred_csv_handles_missing_and_sorts(tmp_path):
    from pcopt.market_sources.fred import parse_fred_csv

    path = tmp_path / "fred.csv"
    path.write_text(
        "observation_date,DEXCHUS\n2024-01-03,7.2\n2024-01-01,.\n2024-01-02,\n",
        encoding="utf-8",
    )
    result = parse_fred_csv(path, "DEXCHUS")
    assert result.index.is_monotonic_increasing
    assert result.isna().tolist() == [True, True, False]
    assert result.iloc[-1] == pytest.approx(7.2)


def test_parse_fred_csv_rejects_duplicate_dates_and_wrong_columns(tmp_path):
    from pcopt.market_sources.fred import parse_fred_csv

    duplicate = tmp_path / "duplicate.csv"
    duplicate.write_text(
        "observation_date,DEXCHUS\n2024-01-01,7.1\n2024-01-01,7.2\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate FRED dates"):
        parse_fred_csv(duplicate, "DEXCHUS")

    wrong = tmp_path / "wrong.csv"
    wrong.write_text("DATE,DEXCHUS\n2024-01-01,7.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected FRED columns"):
        parse_fred_csv(wrong, "DEXCHUS")
