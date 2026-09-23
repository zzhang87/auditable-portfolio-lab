from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from pcopt.data import load_returns_csv
from pcopt.metrics import MetricConfig
from pcopt.optimizer import GeneticOptimizer
from pcopt.replay import build_replay
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

CONSTRAINT_RE = re.compile(r"^([A-Za-z0-9_]+)\s*(<=|>=|<|>|==|=)\s*(-?\d+(?:\.\d+)?)$")


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from error


def parse_objective(items: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in items:
        if "=" in item:
            name, value = item.split("=", 1)
            out[name.strip()] = float(value)
        else:
            out[item.strip()] = 1.0
    return out


def parse_constraints(items: list[str]) -> dict[str, tuple[str, float]]:
    out: dict[str, tuple[str, float]] = {}
    for item in items:
        match = CONSTRAINT_RE.match(item.strip())
        if not match:
            raise argparse.ArgumentTypeError(f"invalid constraint: {item!r}")
        metric, op, bound = match.groups()
        out[metric] = (op, float(bound))
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portfolio optimizer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    optimize = subparsers.add_parser("optimize")
    optimize.add_argument("--returns", required=True, type=Path, help="CSV with year and asset return columns")
    optimize.add_argument("--assets", required=True, help="Comma-separated asset column names to optimize")
    optimize.add_argument(
        "--objective",
        nargs="+",
        default=["cagr=1"],
        help="Metric weights, e.g. cagr=1 ulcer_index=-0.2",
    )
    optimize.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="Constraint such as ulcer_index<=0.08 or standard_deviation<=0.12",
    )
    optimize.add_argument("--rolling-horizon", type=int, default=10)
    optimize.add_argument("--retirement-horizon", type=int, default=30)
    optimize.add_argument("--sensitivity-window", type=int, default=10)
    optimize.add_argument("--population-size", type=int, default=256)
    optimize.add_argument("--generations", type=int, default=200)
    optimize.add_argument(
        "--constraint-tolerance",
        type=float,
        default=1e-6,
        help="Relative tolerance applied to floating-point constraint comparisons",
    )
    optimize.add_argument("--seed", type=int, default=7)
    optimize.add_argument("--db", type=Path, default=Path("data/portfolio_versions.sqlite3"))
    optimize.add_argument("--parent-version-id", type=int)
    optimize.add_argument("--name")
    optimize.add_argument("--notes")
    optimize.set_defaults(handler=run_optimize)

    version_show = subparsers.add_parser("version-show")
    version_show.add_argument("--db", type=Path, default=Path("data/portfolio_versions.sqlite3"))
    version_show.add_argument("--id", required=True, type=int)
    version_show.set_defaults(handler=run_version_show)

    version_children = subparsers.add_parser("version-children")
    version_children.add_argument("--db", type=Path, default=Path("data/portfolio_versions.sqlite3"))
    version_children.add_argument("--id", required=True, type=int)
    version_children.set_defaults(handler=run_version_children)

    version_roots = subparsers.add_parser("version-roots")
    version_roots.add_argument("--db", type=Path, default=Path("data/portfolio_versions.sqlite3"))
    version_roots.set_defaults(handler=run_version_roots)

    run_show = subparsers.add_parser("run-show")
    run_show.add_argument("--db", type=Path, default=Path("data/portfolio_versions.sqlite3"))
    run_show.add_argument("--id", required=True, type=int)
    run_show.set_defaults(handler=run_run_show)

    benchmark = subparsers.add_parser("benchmark")
    benchmark.add_argument("--manifest", required=True, type=Path)
    benchmark.add_argument("--weights", required=True, type=Path)
    benchmark.add_argument("--base-currency", required=True, choices=["USD", "CNY", "both"])
    benchmark.add_argument("--start-year", type=int)
    benchmark.add_argument("--end-year", type=int)
    benchmark.add_argument(
        "--as-of", type=parse_date,
        help="Qualification cutoff (required for raw manifests; built bundles default to coverage_as_of)",
    )
    benchmark.add_argument("--output-dir", required=True, type=Path)
    benchmark.set_defaults(handler=run_benchmark)
    return parser


def run_optimize(args: argparse.Namespace) -> dict[str, object]:
    assets = [item.strip() for item in args.assets.split(",") if item.strip()]
    objective = parse_objective(args.objective)
    constraints = parse_constraints(args.constraint)

    conn = open_database(args.db)
    try:
        initialize_database(conn)
        if args.parent_version_id is not None and get_portfolio_version(conn, args.parent_version_id) is None:
            raise ValueError(f"parent version {args.parent_version_id} not found")

        asset_returns = load_returns_csv(args.returns)

        optimizer = GeneticOptimizer(
            asset_returns=asset_returns,
            assets=assets,
            objective=objective,
            constraints=constraints,
            metric_config=MetricConfig(
                rolling_horizon=args.rolling_horizon,
                retirement_horizon=args.retirement_horizon,
                sensitivity_window=args.sensitivity_window,
            ),
            population_size=args.population_size,
            generations=args.generations,
            constraint_tolerance=args.constraint_tolerance,
            random_seed=args.seed,
        )
        result = optimizer.optimize()

        with conn:
            run_id = create_optimizer_run(
                conn,
                parent_version_id=args.parent_version_id,
                data_source=str(args.returns),
                year_start=int(asset_returns.index.min()),
                year_end=int(asset_returns.index.max()),
                asset_universe=assets,
                objective=objective,
                constraints={metric: list(rule) for metric, rule in constraints.items()},
                optimizer_config={
                    "population_size": optimizer.population_size,
                    "generations": optimizer.generations,
                    "elite_fraction": optimizer.elite_fraction,
                    "mutation_rate": optimizer.mutation_rate,
                    "mutation_scale": optimizer.mutation_scale,
                    "constraint_penalty": optimizer.constraint_penalty,
                    "constraint_tolerance": optimizer.constraint_tolerance,
                    "rolling_horizon": optimizer.metric_config.rolling_horizon,
                    "retirement_horizon": optimizer.metric_config.retirement_horizon,
                    "sensitivity_window": optimizer.metric_config.sensitivity_window,
                },
                random_seed=optimizer.random_seed,
            )
            version_id = create_portfolio_version(
                conn,
                parent_version_id=args.parent_version_id,
                source_run_id=run_id,
                name=args.name,
                weights=result.weights.to_dict(),
                metrics=result.metrics,
                notes=args.notes,
            )
            link_run_result(conn, run_id=run_id, version_id=version_id)
    finally:
        conn.close()

    payload = {
        "version_id": version_id,
        "run_id": run_id,
        "feasible": result.feasible,
        "generation": result.generation,
        "fitness": result.fitness,
        "weights": result.weights.to_dict(),
        "metrics": result.metrics,
    }
    return payload


def run_version_show(args: argparse.Namespace) -> dict[str, object] | None:
    conn = open_database_readonly(args.db)
    try:
        return get_portfolio_version(conn, args.id)
    finally:
        conn.close()


def run_version_children(args: argparse.Namespace) -> list[dict[str, object]]:
    conn = open_database_readonly(args.db)
    try:
        return list_child_versions(conn, args.id)
    finally:
        conn.close()


def run_version_roots(args: argparse.Namespace) -> list[dict[str, object]]:
    conn = open_database_readonly(args.db)
    try:
        return list_root_versions(conn)
    finally:
        conn.close()


def run_run_show(args: argparse.Namespace) -> dict[str, object] | None:
    conn = open_database_readonly(args.db)
    try:
        return get_optimizer_run(conn, args.id)
    finally:
        conn.close()


def run_benchmark(args: argparse.Namespace) -> dict:
    from pcopt.benchmark import evaluate_benchmarks, write_benchmark_report
    from pcopt.market_data import load_market_dataset, load_strict_json

    manifest_path = args.manifest.resolve()
    weights_path = args.weights.resolve()
    output_path = args.output_dir.resolve()
    dataset = load_market_dataset(manifest_path)
    coverage_as_of = dataset.manifest.get("coverage_as_of")
    if args.as_of is None and coverage_as_of is None:
        raise ValueError("--as-of is required for a raw manifest without coverage_as_of")
    requested_as_of = args.as_of or date.fromisoformat(coverage_as_of)
    portfolios = load_strict_json(weights_path)
    report = evaluate_benchmarks(
        dataset,
        portfolios,
        base_currency=args.base_currency,
        start_year=args.start_year,
        end_year=args.end_year,
        as_of=requested_as_of,
    )
    report["reproduce"] = build_replay(
        args,
        report["evaluation"]["as_of"],
        Path.cwd(),
    )
    write_benchmark_report(report, output_path)
    return report


def main() -> None:
    args = build_parser().parse_args()
    payload = args.handler(args)
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
