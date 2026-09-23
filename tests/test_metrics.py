import math

import pandas as pd

from pcopt.data import portfolio_returns
from pcopt.metrics import annualized_return, drawdown_metrics, drawdowns, withdrawal_metrics


def test_initial_loss_counts_in_drawdown_and_ulcer():
    import pytest

    values = [-0.20, 0.10]

    assert drawdowns(values).tolist() == pytest.approx([-0.20, -0.12])
    metrics = drawdown_metrics(values)
    assert metrics["standard_max_drawdown"] == pytest.approx(-0.20)
    assert metrics["ulcer_index"] == pytest.approx(((0.20**2 + 0.12**2) / 2) ** 0.5)


def test_drawdowns_track_initial_wealth_and_later_highs():
    import pytest

    assert drawdowns([0.10, -0.20]).tolist() == pytest.approx([0.0, -0.20])
    assert drawdowns([-0.20, 0.25]).tolist() == pytest.approx([-0.20, 0.0])
    assert drawdowns([0.05, 0.05]).tolist() == pytest.approx([0.0, 0.0])
    assert drawdowns([-0.20]).tolist() == pytest.approx([-0.20])


def test_portfolio_returns_use_annual_rebalance_dot_product():
    returns = pd.DataFrame(
        {
            "A": [0.10, -0.10],
            "B": [0.00, 0.20],
        },
        index=[2000, 2001],
    )

    out = portfolio_returns(returns, {"A": 0.6, "B": 0.4})

    assert math.isclose(out.loc[2000], 0.06)
    assert math.isclose(out.loc[2001], 0.02)


def test_constant_return_cagr_and_drawdown_metrics():
    returns = pd.Series([0.05] * 20, index=range(2000, 2020))

    assert math.isclose(annualized_return(returns), 0.05, rel_tol=1e-12)
    metrics = drawdown_metrics(returns)
    assert metrics["deepest_drawdown"] == 0.0
    assert metrics["standard_max_drawdown"] == 0.0
    assert metrics["longest_drawdown_years"] == 0.0
    assert metrics["ulcer_index"] == 0.0


def test_constant_return_perpetual_withdrawal_rate():
    returns = pd.Series([0.05] * 40, index=range(1980, 2020))

    metrics = withdrawal_metrics(returns, horizon=30)

    assert math.isclose(metrics["perpetual_withdrawal_rate"], 0.05 / 1.05, rel_tol=1e-9)
    assert metrics["safe_withdrawal_rate"] > metrics["perpetual_withdrawal_rate"]
