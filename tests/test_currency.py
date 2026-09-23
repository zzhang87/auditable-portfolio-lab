import pandas as pd
import pytest


def _fx_endpoints():
    return pd.DataFrame(
        {"USD": [1.0, 1.0], "CNY": [7.0, 7.7], "HKD": [7.8, 7.9]},
        index=[2024, 2025],
    )


def test_usd_asset_to_cny_purchasing_power():
    from pcopt.currency import convert_nominal_returns, deflate_returns

    nominal = pd.DataFrame({"US": [0.10]}, index=[2025])
    fx = pd.DataFrame(
        {"USD": [1.0, 1.0], "CNY": [7.0, 7.7], "HKD": [7.8, 7.8]},
        index=[2024, 2025],
    )
    converted = convert_nominal_returns(nominal, {"US": "USD"}, fx, "CNY")
    assert converted.loc[2025, "US"] == pytest.approx(0.21)
    real = deflate_returns(converted, pd.Series({2025: 0.02}))
    assert real.loc[2025, "US"] == pytest.approx(1.21 / 1.02 - 1)


def test_cny_depreciation_offsets_cny_asset_gain_in_usd():
    from pcopt.currency import convert_nominal_returns

    nominal = pd.DataFrame({"CN": [0.10]}, index=[2025])
    fx = pd.DataFrame(
        {"USD": [1.0, 1.0], "CNY": [7.0, 7.7], "HKD": [7.8, 7.8]},
        index=[2024, 2025],
    )
    result = convert_nominal_returns(nominal, {"CN": "CNY"}, fx, "USD")
    assert result.loc[2025, "CN"] == pytest.approx(0.0)


def test_annual_fx_endpoints_selects_latest_common_observation():
    from pcopt.currency import annual_fx_endpoints

    daily = pd.DataFrame(
        {
            "CNY": [7.1, 7.2, None],
            "HKD": [7.8, None, 7.9],
        },
        index=pd.to_datetime(["2025-12-29", "2025-12-30", "2025-12-31"]),
    )
    result = annual_fx_endpoints(daily, [2025])
    assert result.loc[2025].to_dict() == {
        "USD": 1.0,
        "CNY": 7.1,
        "HKD": 7.8,
        "observed_date": "2025-12-29",
    }


def test_annual_fx_endpoints_uses_observed_changing_hkd():
    from pcopt.currency import annual_fx_endpoints

    daily = pd.DataFrame(
        {"CNY": [7.0, 7.0], "HKD": [7.75, 7.85]},
        index=pd.to_datetime(["2024-12-31", "2025-12-31"]),
    )
    result = annual_fx_endpoints(daily, [2024, 2025])
    assert result["HKD"].to_dict() == {2024: 7.75, 2025: 7.85}


def test_annual_fx_endpoints_rejects_eight_day_old_quote():
    from pcopt.currency import annual_fx_endpoints

    daily = pd.DataFrame({"CNY": [7.0], "HKD": [7.8]}, index=pd.to_datetime(["2025-12-23"]))
    with pytest.raises(ValueError, match="missing common FX endpoint for 2025"):
        annual_fx_endpoints(daily, [2025])


@pytest.mark.parametrize("bad_quote", [0.0, -1.0, float("inf")])
def test_annual_fx_endpoints_rejects_nonpositive_or_nonfinite_quotes(bad_quote):
    from pcopt.currency import annual_fx_endpoints

    daily = pd.DataFrame(
        {"CNY": [bad_quote], "HKD": [7.8]},
        index=pd.to_datetime(["2025-12-31"]),
    )
    with pytest.raises(ValueError, match="positive and finite"):
        annual_fx_endpoints(daily, [2025])


def test_annual_fx_endpoints_rejects_duplicate_dates():
    from pcopt.currency import annual_fx_endpoints

    daily = pd.DataFrame(
        {"CNY": [7.0, 7.1], "HKD": [7.8, 7.9]},
        index=pd.to_datetime(["2025-12-31", "2025-12-31"]),
    )
    with pytest.raises(ValueError, match="duplicate FX dates"):
        annual_fx_endpoints(daily, [2025])


def test_annual_fx_endpoints_rejects_equivalent_date_labels():
    from pcopt.currency import annual_fx_endpoints

    daily = pd.DataFrame(
        {"CNY": [7.0, 7.1], "HKD": [7.8, 7.9]},
        index=["2025-12-31", pd.Timestamp("2025-12-31")],
    )
    with pytest.raises(ValueError, match="duplicate FX dates"):
        annual_fx_endpoints(daily, [2025])


def test_same_currency_conversion_is_identity_and_does_not_mutate_inputs():
    from pcopt.currency import convert_nominal_returns

    nominal = pd.DataFrame({"US": [0.1]}, index=[2025])
    fx = _fx_endpoints()
    nominal_before = nominal.copy(deep=True)
    fx_before = fx.copy(deep=True)
    result = convert_nominal_returns(nominal, {"US": "USD"}, fx, "USD")
    pd.testing.assert_frame_equal(result, nominal)
    pd.testing.assert_frame_equal(nominal, nominal_before)
    pd.testing.assert_frame_equal(fx, fx_before)


def test_cross_currency_round_trip_recovers_original_growth_factor():
    from pcopt.currency import convert_nominal_returns

    usd = pd.DataFrame({"asset": [0.23]}, index=[2025])
    in_cny = convert_nominal_returns(usd, {"asset": "USD"}, _fx_endpoints(), "CNY")
    back_to_usd = convert_nominal_returns(in_cny, {"asset": "CNY"}, _fx_endpoints(), "USD")
    assert back_to_usd.loc[2025, "asset"] == pytest.approx(0.23)


def test_observed_hkd_change_affects_conversion():
    from pcopt.currency import convert_nominal_returns

    nominal = pd.DataFrame({"HK": [0.0]}, index=[2025])
    result = convert_nominal_returns(nominal, {"HK": "HKD"}, _fx_endpoints(), "USD")
    assert result.loc[2025, "HK"] == pytest.approx(7.8 / 7.9 - 1)


def test_common_weight_portfolio_conversion_matches_asset_conversions():
    from pcopt.currency import convert_nominal_returns

    local = pd.DataFrame({"A": [0.10], "B": [-0.05]}, index=[2025])
    weights = pd.Series({"A": 0.4, "B": 0.6})
    converted_assets = convert_nominal_returns(local, {"A": "USD", "B": "USD"}, _fx_endpoints(), "CNY")
    converted_portfolio = convert_nominal_returns(
        pd.DataFrame({"portfolio": [(local.loc[2025] * weights).sum()]}, index=[2025]),
        {"portfolio": "USD"},
        _fx_endpoints(),
        "CNY",
    )
    assert (converted_assets.loc[2025] * weights).sum() == pytest.approx(converted_portfolio.loc[2025, "portfolio"])


def test_conversion_rejects_missing_currency_mapping():
    from pcopt.currency import convert_nominal_returns

    with pytest.raises(ValueError, match="missing currency mapping for US"):
        convert_nominal_returns(pd.DataFrame({"US": [0.1]}, index=[2025]), {}, _fx_endpoints(), "USD")


def test_conversion_rejects_missing_previous_year_fx():
    from pcopt.currency import convert_nominal_returns

    with pytest.raises(ValueError, match="missing FX endpoint: US/2025"):
        convert_nominal_returns(
            pd.DataFrame({"US": [0.1]}, index=[2025]),
            {"US": "USD"},
            _fx_endpoints().loc[[2025]],
            "CNY",
        )


def test_conversion_rejects_duplicate_return_and_fx_years():
    from pcopt.currency import convert_nominal_returns

    duplicate_returns = pd.DataFrame({"US": [0.1, 0.2]}, index=[2025, 2025])
    with pytest.raises(ValueError, match="duplicate return years"):
        convert_nominal_returns(duplicate_returns, {"US": "USD"}, _fx_endpoints(), "USD")
    duplicate_fx = pd.concat([_fx_endpoints(), _fx_endpoints().loc[[2025]]])
    with pytest.raises(ValueError, match="duplicate FX years"):
        convert_nominal_returns(
            pd.DataFrame({"US": [0.1]}, index=[2025]),
            {"US": "USD"},
            duplicate_fx,
            "USD",
        )


@pytest.mark.parametrize("bad_return", [-1.0, float("nan"), float("inf")])
def test_conversion_rejects_invalid_nominal_returns(bad_return):
    from pcopt.currency import convert_nominal_returns

    with pytest.raises(ValueError, match="invalid nominal observation"):
        convert_nominal_returns(
            pd.DataFrame({"US": [bad_return]}, index=[2025]),
            {"US": "USD"},
            _fx_endpoints(),
            "USD",
        )


def test_conversion_rejects_unsupported_base_local_and_invalid_fx():
    from pcopt.currency import convert_nominal_returns

    nominal = pd.DataFrame({"asset": [0.1]}, index=[2025])
    with pytest.raises(ValueError, match="base currency must be USD or CNY"):
        convert_nominal_returns(nominal, {"asset": "USD"}, _fx_endpoints(), "HKD")
    with pytest.raises(ValueError, match="unsupported currency for asset"):
        convert_nominal_returns(nominal, {"asset": "EUR"}, _fx_endpoints(), "USD")
    invalid_fx = _fx_endpoints()
    invalid_fx.loc[2025, "CNY"] = 0.0
    with pytest.raises(ValueError, match="invalid FX endpoint"):
        convert_nominal_returns(nominal, {"asset": "USD"}, invalid_fx, "CNY")


def test_conversion_rejects_nonnumeric_fx_endpoint():
    from pcopt.currency import convert_nominal_returns

    fx = _fx_endpoints().astype(object)
    fx.loc[2025, "CNY"] = "7.7"
    with pytest.raises(ValueError, match="invalid FX endpoint"):
        convert_nominal_returns(
            pd.DataFrame({"asset": [0.1]}, index=[2025]),
            {"asset": "USD"},
            fx,
            "CNY",
        )


def test_deflation_and_zero_cpi_and_no_input_mutation():
    from pcopt.currency import deflate_returns

    nominal = pd.DataFrame({"asset": [0.1, -0.05]}, index=[2024, 2025])
    inflation = pd.Series({2024: 0.0, 2025: 0.025})
    nominal_before = nominal.copy(deep=True)
    inflation_before = inflation.copy(deep=True)
    result = deflate_returns(nominal, inflation)
    assert result.loc[2024, "asset"] == pytest.approx(0.1)
    assert result.loc[2025, "asset"] == pytest.approx(0.95 / 1.025 - 1)
    pd.testing.assert_frame_equal(nominal, nominal_before)
    pd.testing.assert_series_equal(inflation, inflation_before)


def test_deflation_rejects_duplicate_missing_or_invalid_inflation():
    from pcopt.currency import deflate_returns

    nominal = pd.DataFrame({"asset": [0.1]}, index=[2025])
    duplicate = pd.Series([0.02, 0.03], index=[2025, 2025])
    with pytest.raises(ValueError, match="duplicate inflation years"):
        deflate_returns(nominal, duplicate)
    for inflation in (pd.Series(dtype=float), pd.Series({2025: -1.0})):
        with pytest.raises(ValueError, match="missing or invalid inflation"):
            deflate_returns(nominal, inflation)


@pytest.mark.parametrize("bad_return", [-1.0, float("nan"), float("inf")])
def test_deflation_rejects_invalid_nominal_return(bad_return):
    from pcopt.currency import deflate_returns

    with pytest.raises(ValueError, match="invalid nominal returns"):
        deflate_returns(
            pd.DataFrame({"asset": [bad_return]}, index=[2025]),
            pd.Series({2025: 0.02}),
        )
