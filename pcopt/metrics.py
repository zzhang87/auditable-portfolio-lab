from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MetricConfig:
    """Configuration for metrics that depend on an investing horizon."""

    rolling_horizon: int = 10
    retirement_horizon: int = 30
    sensitivity_window: int = 10
    std_ddof: int = 1


def _as_returns(returns: Iterable[float] | pd.Series) -> pd.Series:
    out = pd.Series(returns, dtype=float).dropna()
    if out.empty:
        raise ValueError("at least one return is required")
    if (out <= -1.0).any():
        raise ValueError("returns less than or equal to -100% are not supported")
    return out


def wealth_index(returns: Iterable[float] | pd.Series, *, initial: float = 1.0) -> pd.Series:
    """Compound annual returns into a real wealth index."""

    r = _as_returns(returns)
    return (initial * (1.0 + r).cumprod()).rename("wealth")


def annualized_return(returns: Iterable[float] | pd.Series) -> float:
    """Compound annual growth rate over the full return series."""

    r = _as_returns(returns)
    return float(np.prod(1.0 + r) ** (1.0 / len(r)) - 1.0)


def arithmetic_average_return(returns: Iterable[float] | pd.Series) -> float:
    return float(_as_returns(returns).mean())


def standard_deviation(returns: Iterable[float] | pd.Series, *, ddof: int = 1) -> float:
    r = _as_returns(returns)
    if len(r) <= ddof:
        return 0.0
    return float(r.std(ddof=ddof))


def rolling_cagr(returns: Iterable[float] | pd.Series, horizon: int) -> pd.Series:
    """Real CAGR for every full rolling period of `horizon` years."""

    if horizon <= 0:
        raise ValueError("horizon must be positive")
    r = _as_returns(returns)
    if len(r) < horizon:
        raise ValueError(f"not enough data for {horizon}-year rolling CAGR")

    values: list[float] = []
    years: list[int] = []
    for start in range(0, len(r) - horizon + 1):
        window = r.iloc[start : start + horizon]
        values.append(annualized_return(window))
        years.append(int(r.index[start]) if np.issubdtype(r.index.dtype, np.integer) else start)
    return pd.Series(values, index=years, name=f"rolling_cagr_{horizon}")


def rolling_cagr_percentiles(returns: Iterable[float] | pd.Series, horizon: int) -> dict[str, float]:
    """Minimum, 15th percentile, median, 85th percentile, and maximum rolling CAGR."""

    values = rolling_cagr(returns, horizon).to_numpy()
    return {
        "rolling_cagr_min": float(np.min(values)),
        "rolling_cagr_baseline": float(np.percentile(values, 15)),
        "rolling_cagr_median": float(np.percentile(values, 50)),
        "rolling_cagr_stretch": float(np.percentile(values, 85)),
        "rolling_cagr_max": float(np.max(values)),
    }


def drawdowns(returns: Iterable[float] | pd.Series) -> pd.Series:
    """Year-end drawdowns from initial wealth 1 and subsequent running highs."""

    wealth = wealth_index(returns)
    peaks = wealth.cummax().clip(lower=1.0)
    dd = wealth / peaks - 1.0
    return dd.rename("drawdown")


def _start_date_drawdown_metrics(returns: pd.Series) -> tuple[float, int]:
    """Portfolio Charts-style loss metrics across every possible start year.

    Each start year is treated as a new investor with initial value 1. The
    deepest drawdown is the worst real compound loss from any start. The longest
    drawdown waits for durable recovery: if the path briefly rises above 1 and
    later falls below it again, the unresolved loss duration continues until the
    final year below 1.
    """

    r = _as_returns(returns)
    deepest = 0.0
    longest = 0

    for start in range(len(r)):
        path = (1.0 + r.iloc[start:]).cumprod()
        if path.empty:
            continue
        deepest = min(deepest, float(path.min() - 1.0))
        below = np.flatnonzero(path.to_numpy() < 1.0)
        if len(below):
            longest = max(longest, int(below[-1] + 1))

    return deepest, longest


def drawdown_metrics(returns: Iterable[float] | pd.Series) -> dict[str, float]:
    """Deepest drawdown, longest drawdown, and ulcer index.

    The ulcer index uses year-end drawdowns from the running high-water mark and
    returns a decimal value. For display as a percentage, multiply by 100.
    """

    r = _as_returns(returns)
    dd = drawdowns(r)
    pc_deepest, pc_longest = _start_date_drawdown_metrics(r)
    ulcer = float(np.sqrt(np.mean(np.square(np.minimum(dd.to_numpy(), 0.0)))))
    return {
        "deepest_drawdown": pc_deepest,
        "standard_max_drawdown": float(dd.min()),
        "longest_drawdown_years": float(pc_longest),
        "ulcer_index": ulcer,
    }


def start_date_sensitivity(returns: Iterable[float] | pd.Series, window: int = 10) -> dict[str, float]:
    """Difference between forward and backward `window`-year CAGRs.

    Smaller spreads indicate less dependence on lucky start dates.
    """

    if window <= 0:
        raise ValueError("window must be positive")
    r = _as_returns(returns)
    if len(r) < window * 2:
        raise ValueError(f"not enough data for {window}-year start-date sensitivity")

    diffs: list[float] = []
    for anchor in range(window, len(r) - window + 1):
        backward = annualized_return(r.iloc[anchor - window : anchor])
        forward = annualized_return(r.iloc[anchor : anchor + window])
        diffs.append(forward - backward)

    luckiest = float(np.max(diffs))
    unluckiest = float(np.min(diffs))
    return {
        "luckiest_start": luckiest,
        "unluckiest_start": unluckiest,
        "start_date_sensitivity": luckiest - unluckiest,
    }


def _terminal_balance(returns: np.ndarray, withdrawal_rate: float) -> float:
    balance = 1.0
    for ret in returns:
        balance -= withdrawal_rate
        balance *= 1.0 + ret
    return float(balance)


def _solve_withdrawal_rate(returns: np.ndarray, target_terminal_balance: float) -> float:
    """Solve fixed real withdrawal rate by bisection."""

    low = 0.0
    high = 1.0
    for _ in range(80):
        mid = (low + high) / 2.0
        terminal = _terminal_balance(returns, mid)
        if terminal >= target_terminal_balance:
            low = mid
        else:
            high = mid
    return low


def rolling_withdrawal_rates(returns: Iterable[float] | pd.Series, horizon: int) -> pd.DataFrame:
    """SWR and PWR for each full rolling retirement period.

    Expenses are set aside at the beginning of every year and held in a separate
    zero-interest account. Returns are real, so the withdrawal amount is constant
    in purchasing-power terms.
    """

    if horizon <= 0:
        raise ValueError("horizon must be positive")
    r = _as_returns(returns)
    if len(r) < horizon:
        raise ValueError(f"not enough data for {horizon}-year withdrawal rates")

    rows: list[dict[str, float]] = []
    for start in range(0, len(r) - horizon + 1):
        window = r.iloc[start : start + horizon].to_numpy(dtype=float)
        swr = _solve_withdrawal_rate(window, 0.0)
        pwr = _solve_withdrawal_rate(window, 1.0)
        rows.append(
            {
                "start": int(r.index[start]) if np.issubdtype(r.index.dtype, np.integer) else start,
                "safe_withdrawal_rate": swr,
                "perpetual_withdrawal_rate": pwr,
            }
        )

    return pd.DataFrame(rows).set_index("start")


def withdrawal_metrics(returns: Iterable[float] | pd.Series, horizon: int = 30) -> dict[str, float]:
    rates = rolling_withdrawal_rates(returns, horizon)
    swr = float(rates["safe_withdrawal_rate"].min())
    pwr = float(rates["perpetual_withdrawal_rate"].min())
    return {
        "safe_withdrawal_rate": swr,
        "perpetual_withdrawal_rate": pwr,
        "long_term_withdrawal_rate": max(0.0, annualized_return(returns) / (1.0 + annualized_return(returns))),
    }


def metric_snapshot(returns: Iterable[float] | pd.Series, config: MetricConfig | None = None) -> dict[str, float]:
    """Compute the main Portfolio Charts-style metrics for one return series."""

    cfg = config or MetricConfig()
    r = _as_returns(returns)
    out = {
        "cagr": annualized_return(r),
        "average_return": arithmetic_average_return(r),
        "standard_deviation": standard_deviation(r, ddof=cfg.std_ddof),
    }
    if len(r) >= cfg.rolling_horizon:
        out.update(rolling_cagr_percentiles(r, cfg.rolling_horizon))
    out.update(drawdown_metrics(r))
    if len(r) >= cfg.sensitivity_window * 2:
        out.update(start_date_sensitivity(r, cfg.sensitivity_window))
    if len(r) >= cfg.retirement_horizon:
        out.update(withdrawal_metrics(r, cfg.retirement_horizon))
    return out
