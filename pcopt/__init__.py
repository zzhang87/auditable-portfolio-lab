"""Portfolio Charts-style portfolio analytics and optimization."""

from pcopt.data import load_returns_csv, portfolio_returns
from pcopt.metrics import (
    MetricConfig,
    annualized_return,
    drawdown_metrics,
    metric_snapshot,
    start_date_sensitivity,
    withdrawal_metrics,
)
from pcopt.market_data import MarketDataset, build_market_dataset, load_market_dataset
from pcopt.optimizer import GeneticOptimizer, OptimizationResult
from pcopt.public_data import (
    build_us_public_proxy_returns,
    source_catalog,
    write_us_public_proxy_returns,
)
from pcopt.simba import (
    DEFAULT_PORTFOLIO_CHARTS_ASSET_CODES,
    SIMBA_SERIES_MAPPING,
    build_simba_proxy_returns,
    load_simba_data_series,
    write_simba_proxy_returns,
)
from pcopt.storage import (
    create_optimizer_run,
    create_portfolio_version,
    get_optimizer_run,
    get_portfolio_version,
    initialize_database,
    link_run_result,
    list_child_versions,
    list_root_versions,
    open_database,
    open_database_readonly,
)

__all__ = [
    "GeneticOptimizer",
    "MetricConfig",
    "MarketDataset",
    "OptimizationResult",
    "annualized_return",
    "build_market_dataset",
    "drawdown_metrics",
    "load_returns_csv",
    "load_market_dataset",
    "metric_snapshot",
    "portfolio_returns",
    "create_optimizer_run",
    "create_portfolio_version",
    "get_optimizer_run",
    "get_portfolio_version",
    "initialize_database",
    "link_run_result",
    "list_child_versions",
    "list_root_versions",
    "open_database",
    "open_database_readonly",
    "build_us_public_proxy_returns",
    "build_simba_proxy_returns",
    "DEFAULT_PORTFOLIO_CHARTS_ASSET_CODES",
    "load_simba_data_series",
    "SIMBA_SERIES_MAPPING",
    "source_catalog",
    "start_date_sensitivity",
    "withdrawal_metrics",
    "write_simba_proxy_returns",
    "write_us_public_proxy_returns",
]
