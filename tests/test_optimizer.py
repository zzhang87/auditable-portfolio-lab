import pandas as pd
import pytest

from pcopt.metrics import MetricConfig
from pcopt.optimizer import GeneticOptimizer


def test_cli_persists_final_result_to_database(tmp_path):
    from pcopt import cli
    from pcopt.storage import get_optimizer_run, get_portfolio_version, open_database

    returns_path = tmp_path / "returns.csv"
    returns_path.write_text(
        "year,USA-LCB,USA-LTT\n2020,0.10,0.02\n2021,0.05,0.03\n2022,-0.02,0.01\n2023,0.08,0.04\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "versions.sqlite3"

    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "optimize",
            "--returns",
            str(returns_path),
            "--assets",
            "USA-LCB,USA-LTT",
            "--objective",
            "cagr=1",
            "--constraint",
            "ulcer_index<=0.05",
            "--rolling-horizon",
            "2",
            "--retirement-horizon",
            "2",
            "--sensitivity-window",
            "2",
            "--population-size",
            "4",
            "--generations",
            "1",
            "--constraint-tolerance",
            "1e-5",
            "--seed",
            "13",
            "--db",
            str(db_path),
            "--name",
            "first saved result",
            "--notes",
            "saved from cli",
        ]
    )

    payload = cli.run_optimize(args)

    conn = open_database(db_path)
    run = get_optimizer_run(conn, payload["run_id"])
    version = get_portfolio_version(conn, payload["version_id"])

    assert payload["version_id"] == 1
    assert run["data_source"] == str(returns_path)
    assert run["year_start"] == 2020
    assert run["year_end"] == 2023
    assert run["asset_universe"] == ["USA-LCB", "USA-LTT"]
    assert run["objective"] == {"cagr": 1.0}
    assert run["constraints"] == {"ulcer_index": ["<=", 0.05]}
    assert run["random_seed"] == 13
    assert run["optimizer_config"] == {
        "constraint_penalty": 1000.0,
        "constraint_tolerance": 1e-05,
        "elite_fraction": 0.1,
        "generations": 1,
        "mutation_rate": 0.2,
        "mutation_scale": 0.08,
        "population_size": 4,
        "retirement_horizon": 2,
        "rolling_horizon": 2,
        "sensitivity_window": 2,
    }
    assert run["result_version_id"] == payload["version_id"]
    assert version["name"] == "first saved result"
    assert version["parent_version_id"] is None
    assert version["source_run_id"] == payload["run_id"]
    assert version["notes"] == "saved from cli"


def test_cli_persists_child_lineage_when_parent_version_id_is_provided(tmp_path):
    from pcopt import cli
    from pcopt.storage import get_optimizer_run, get_portfolio_version, open_database

    returns_path = tmp_path / "returns.csv"
    returns_path.write_text(
        "year,USA-LCB,USA-LTT\n2020,0.10,0.02\n2021,0.05,0.03\n2022,-0.02,0.01\n2023,0.08,0.04\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "versions.sqlite3"
    parser = cli.build_parser()

    root_args = parser.parse_args(
        [
            "optimize",
            "--returns",
            str(returns_path),
            "--assets",
            "USA-LCB,USA-LTT",
            "--objective",
            "cagr=1",
            "--rolling-horizon",
            "2",
            "--retirement-horizon",
            "2",
            "--sensitivity-window",
            "2",
            "--population-size",
            "4",
            "--generations",
            "1",
            "--seed",
            "21",
            "--db",
            str(db_path),
            "--name",
            "root",
        ]
    )
    root_payload = cli.run_optimize(root_args)

    child_args = parser.parse_args(
        [
            "optimize",
            "--returns",
            str(returns_path),
            "--assets",
            "USA-LCB,USA-LTT",
            "--objective",
            "cagr=1",
            "--rolling-horizon",
            "2",
            "--retirement-horizon",
            "2",
            "--sensitivity-window",
            "2",
            "--population-size",
            "4",
            "--generations",
            "1",
            "--seed",
            "22",
            "--db",
            str(db_path),
            "--parent-version-id",
            str(root_payload["version_id"]),
            "--name",
            "child",
        ]
    )
    child_payload = cli.run_optimize(child_args)

    conn = open_database(db_path)
    child_run = get_optimizer_run(conn, child_payload["run_id"])
    child_version = get_portfolio_version(conn, child_payload["version_id"])

    assert child_run["parent_version_id"] == root_payload["version_id"]
    assert child_version["parent_version_id"] == root_payload["version_id"]


def test_cli_rejects_missing_parent_version_before_loading_returns(monkeypatch, tmp_path):
    from pcopt import cli

    parser = cli.build_parser()
    db_path = tmp_path / "versions.sqlite3"
    args = parser.parse_args(
        [
            "optimize",
            "--returns",
            str(tmp_path / "returns.csv"),
            "--assets",
            "USA-LCB,USA-LTT",
            "--objective",
            "cagr=1",
            "--db",
            str(db_path),
            "--parent-version-id",
            "999",
        ]
    )

    monkeypatch.setattr(
        cli,
        "load_returns_csv",
        lambda path: (_ for _ in ()).throw(AssertionError("load_returns_csv should not run")),
    )
    monkeypatch.setattr(
        cli,
        "GeneticOptimizer",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("GeneticOptimizer should not run")),
    )

    with pytest.raises(ValueError, match="parent version 999 not found"):
        cli.run_optimize(args)


def test_optimize_then_version_show_round_trip(tmp_path):
    from pcopt import cli

    returns_path = tmp_path / "returns.csv"
    returns_path.write_text(
        "year,USA-LCB,USA-LTT\n2020,0.10,0.02\n2021,0.05,0.03\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "versions.sqlite3"
    parser = cli.build_parser()

    optimize_args = parser.parse_args(
        [
            "optimize",
            "--returns",
            str(returns_path),
            "--assets",
            "USA-LCB,USA-LTT",
            "--objective",
            "cagr=1",
            "--rolling-horizon",
            "2",
            "--retirement-horizon",
            "2",
            "--sensitivity-window",
            "2",
            "--population-size",
            "4",
            "--generations",
            "1",
            "--db",
            str(db_path),
            "--name",
            "round-trip",
        ]
    )
    optimize_payload = cli.run_optimize(optimize_args)

    show_args = parser.parse_args(["version-show", "--db", str(db_path), "--id", str(optimize_payload["version_id"])])
    show_payload = cli.run_version_show(show_args)

    assert show_payload["name"] == "round-trip"
    assert set(show_payload["weights"]) == {"USA-LCB", "USA-LTT"}


def test_run_optimize_closes_database_connection_when_persistence_fails(monkeypatch, tmp_path):
    from argparse import Namespace

    from pcopt import cli

    class DummyOptimizer:
        def __init__(self):
            self.population_size = 4
            self.generations = 1
            self.elite_fraction = 0.1
            self.mutation_rate = 0.2
            self.mutation_scale = 0.08
            self.constraint_penalty = 1000.0
            self.constraint_tolerance = 1e-6
            self.metric_config = MetricConfig(
                rolling_horizon=2,
                retirement_horizon=2,
                sensitivity_window=1,
            )
            self.random_seed = 7

        def optimize(self):
            return Namespace(
                weights=pd.Series({"USA-LCB": 1.0}),
                metrics={"cagr": 0.1},
                feasible=True,
                generation=1,
                fitness=0.1,
            )

    class TrackingConnection:
        def __init__(self):
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def close(self):
            self.closed = True

    conn = TrackingConnection()

    monkeypatch.setattr(
        cli,
        "load_returns_csv",
        lambda path: pd.DataFrame({"USA-LCB": [0.1, 0.2]}, index=[2020, 2021]),
    )
    monkeypatch.setattr(cli, "GeneticOptimizer", lambda **kwargs: DummyOptimizer())
    monkeypatch.setattr(cli, "open_database", lambda path: conn)
    monkeypatch.setattr(cli, "initialize_database", lambda db: None)
    monkeypatch.setattr(
        cli, "create_optimizer_run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    args = Namespace(
        returns=tmp_path / "returns.csv",
        assets="USA-LCB",
        objective=["cagr=1"],
        constraint=[],
        rolling_horizon=2,
        retirement_horizon=2,
        sensitivity_window=1,
        population_size=4,
        generations=1,
        constraint_tolerance=1e-6,
        seed=7,
        db=tmp_path / "versions.sqlite3",
        parent_version_id=None,
        name=None,
        notes=None,
    )

    with pytest.raises(RuntimeError, match="boom"):
        cli.run_optimize(args)

    assert conn.closed


def test_optimizer_returns_feasible_candidate_under_ulcer_constraint():
    returns = pd.DataFrame(
        {
            "steady": [0.03] * 36,
            "growth": [0.18, -0.12, 0.16, -0.10] * 9,
            "cash": [0.01] * 36,
        },
        index=range(1988, 2024),
    )

    result = GeneticOptimizer(
        asset_returns=returns,
        assets=["steady", "growth", "cash"],
        objective={"cagr": 1.0},
        constraints={"ulcer_index": ("<=", 0.04)},
        metric_config=MetricConfig(rolling_horizon=5, retirement_horizon=20, sensitivity_window=5),
        population_size=48,
        generations=25,
        random_seed=11,
    ).optimize()

    assert result.feasible
    assert result.metrics["ulcer_index"] <= 0.040000001
    assert abs(float(result.weights.sum()) - 1.0) < 1e-12
    assert (result.weights >= 0).all()


def test_constraint_violation_allows_rounding_at_non_strict_boundary():
    returns = pd.DataFrame({"asset": [0.04] * 20}, index=range(2000, 2020))
    optimizer = GeneticOptimizer(
        asset_returns=returns,
        assets=["asset"],
        objective={"cagr": 1.0},
        constraints={"cagr": ("<=", 0.04)},
        population_size=4,
        generations=1,
    )

    feasible, violation = optimizer._constraint_violation({"cagr": 0.040000000000000036})

    assert feasible
    assert violation == 0.0


def test_constraint_violation_uses_tolerance_for_equality():
    returns = pd.DataFrame(
        {
            "growth": [0.10] * 20,
            "cash": [0.00] * 20,
        },
        index=range(2000, 2020),
    )
    optimizer = GeneticOptimizer(
        asset_returns=returns,
        assets=["growth", "cash"],
        objective={"cagr": 1.0},
        constraints={"average_return": ("==", 0.05)},
        population_size=4,
        generations=1,
    )

    feasible, violation = optimizer._constraint_violation({"average_return": 0.0500004})

    assert feasible
    assert violation == 0.0


def test_constraint_violation_keeps_strict_operators_distinct():
    returns = pd.DataFrame({"asset": [0.04] * 20}, index=range(2000, 2020))

    lt_optimizer = GeneticOptimizer(
        asset_returns=returns,
        assets=["asset"],
        objective={"cagr": 1.0},
        constraints={"cagr": ("<", 0.04)},
        population_size=4,
        generations=1,
    )
    lt_boundary, _ = lt_optimizer._constraint_violation({"cagr": 0.04})
    lt_clear, _ = lt_optimizer._constraint_violation({"cagr": 0.039998})

    gt_optimizer = GeneticOptimizer(
        asset_returns=returns,
        assets=["asset"],
        objective={"cagr": 1.0},
        constraints={"cagr": (">", 0.04)},
        population_size=4,
        generations=1,
    )
    gt_boundary, _ = gt_optimizer._constraint_violation({"cagr": 0.04})
    gt_clear, _ = gt_optimizer._constraint_violation({"cagr": 0.040002})

    assert not lt_boundary
    assert lt_clear
    assert not gt_boundary
    assert gt_clear


def test_optimizer_treats_non_strict_boundary_solution_as_feasible():
    returns = pd.DataFrame({"asset": [0.04] * 20}, index=range(2000, 2020))

    result = GeneticOptimizer(
        asset_returns=returns,
        assets=["asset"],
        objective={"cagr": 1.0},
        constraints={"cagr": ("<=", 0.04)},
        metric_config=MetricConfig(rolling_horizon=5, retirement_horizon=10, sensitivity_window=5),
        population_size=8,
        generations=2,
        random_seed=1,
    ).optimize()

    assert result.feasible
