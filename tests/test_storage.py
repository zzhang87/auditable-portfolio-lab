import sqlite3

import pytest


def _create_lineage_fixture(db_path):
    from pcopt.storage import (
        create_optimizer_run,
        create_portfolio_version,
        initialize_database,
        link_run_result,
        open_database,
    )

    conn = open_database(db_path)
    initialize_database(conn)

    root_run_id = create_optimizer_run(
        conn,
        parent_version_id=None,
        data_source="data/us_public_proxy_returns.csv",
        year_start=1970,
        year_end=2025,
        asset_universe=["USA-LCB", "USA-LTT"],
        objective={"cagr": 1.0},
        constraints={"ulcer_index": ["<", 0.05]},
        optimizer_config={"population_size": 32},
        random_seed=7,
    )
    root_version_id = create_portfolio_version(
        conn,
        parent_version_id=None,
        source_run_id=root_run_id,
        name="root",
        weights={"USA-LCB": 0.5, "USA-LTT": 0.5},
        metrics={"cagr": 0.07},
        notes=None,
    )
    link_run_result(conn, run_id=root_run_id, version_id=root_version_id)

    child_run_id = create_optimizer_run(
        conn,
        parent_version_id=root_version_id,
        data_source="data/us_public_proxy_returns.csv",
        year_start=1970,
        year_end=2025,
        asset_universe=["USA-LCB", "USA-LTT", "GLO-GLD"],
        objective={"cagr": 1.0},
        constraints={},
        optimizer_config={"population_size": 48},
        random_seed=8,
    )
    child_version_id = create_portfolio_version(
        conn,
        parent_version_id=root_version_id,
        source_run_id=child_run_id,
        name="child",
        weights={"USA-LCB": 0.4, "USA-LTT": 0.4, "GLO-GLD": 0.2},
        metrics={"cagr": 0.08},
        notes="derived",
    )
    link_run_result(conn, run_id=child_run_id, version_id=child_version_id)
    conn.commit()
    conn.close()

    return {
        "root_run_id": root_run_id,
        "root_version_id": root_version_id,
        "child_run_id": child_run_id,
        "child_version_id": child_version_id,
    }


def test_initialize_database_creates_expected_tables(tmp_path):
    from pcopt.storage import initialize_database, open_database

    conn = open_database(tmp_path / "versions.sqlite3")
    initialize_database(conn)

    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {row[0] for row in rows}

    assert {"schema_meta", "optimizer_runs", "portfolio_versions"}.issubset(names)
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    assert tuple(version) == ("1",)


def test_initialize_database_preserves_existing_schema_version(tmp_path):
    from pcopt.storage import initialize_database, open_database

    conn = open_database(tmp_path / "versions.sqlite3")
    initialize_database(conn)

    conn.execute("UPDATE schema_meta SET value = '1' WHERE key = 'schema_version'")
    conn.commit()

    initialize_database(conn)

    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    assert tuple(version) == ("1",)


def test_initialize_database_rejects_unknown_schema_version(tmp_path):
    from pcopt.storage import initialize_database, open_database

    conn = open_database(tmp_path / "versions.sqlite3")
    initialize_database(conn)
    conn.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")
    conn.commit()

    with pytest.raises(RuntimeError, match="Unsupported schema version"):
        initialize_database(conn)


def test_create_root_and_child_versions_round_trip(tmp_path):
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
    )

    db_path = tmp_path / "versions.sqlite3"
    conn = open_database(db_path)
    initialize_database(conn)

    root_run_id = create_optimizer_run(
        conn,
        parent_version_id=None,
        data_source="data/us_public_proxy_returns.csv",
        year_start=1970,
        year_end=2025,
        asset_universe=["USA-LCB", "USA-LTT"],
        objective={"cagr": 1.0},
        constraints={"ulcer_index": ["<", 0.05]},
        optimizer_config={"population_size": 32},
        random_seed=7,
    )
    root_version_id = create_portfolio_version(
        conn,
        parent_version_id=None,
        source_run_id=root_run_id,
        name="root",
        weights={"USA-LCB": 0.5, "USA-LTT": 0.5},
        metrics={"cagr": 0.07},
        notes=None,
    )
    link_run_result(conn, run_id=root_run_id, version_id=root_version_id)

    child_run_id = create_optimizer_run(
        conn,
        parent_version_id=root_version_id,
        data_source="data/us_public_proxy_returns.csv",
        year_start=1970,
        year_end=2025,
        asset_universe=["USA-LCB", "USA-LTT", "GLO-GLD"],
        objective={"cagr": 1.0},
        constraints={},
        optimizer_config={"population_size": 32},
        random_seed=8,
    )
    child_version_id = create_portfolio_version(
        conn,
        parent_version_id=root_version_id,
        source_run_id=child_run_id,
        name="child",
        weights={"USA-LCB": 0.4, "USA-LTT": 0.4, "GLO-GLD": 0.2},
        metrics={"cagr": 0.08},
        notes="derived",
    )
    link_run_result(conn, run_id=child_run_id, version_id=child_version_id)

    conn.commit()
    conn.close()

    conn = open_database(db_path)

    root = get_portfolio_version(conn, root_version_id)
    root_run = get_optimizer_run(conn, root_run_id)
    children = list_child_versions(conn, root_version_id)
    roots = list_root_versions(conn)

    assert root["id"] == root_version_id
    assert root["parent_version_id"] is None
    assert root["weights"] == {"USA-LCB": 0.5, "USA-LTT": 0.5}
    assert root["metrics"] == {"cagr": 0.07}
    assert root_run["id"] == root_run_id
    assert root_run["parent_version_id"] is None
    assert root_run["result_version_id"] == root_version_id
    assert root_run["asset_universe"] == ["USA-LCB", "USA-LTT"]
    assert root_run["objective"] == {"cagr": 1.0}
    assert root_run["constraints"] == {"ulcer_index": ["<", 0.05]}
    assert root_run["optimizer_config"] == {"population_size": 32}
    assert roots[0]["id"] == root_version_id
    assert roots[0]["parent_version_id"] is None
    assert children[0]["id"] == child_version_id
    assert children[0]["parent_version_id"] == root_version_id
    assert children[0]["weights"] == {"USA-LCB": 0.4, "USA-LTT": 0.4, "GLO-GLD": 0.2}
    assert children[0]["metrics"] == {"cagr": 0.08}


def test_transaction_rollback_leaves_no_partial_persistence(tmp_path):
    from pcopt.storage import (
        create_optimizer_run,
        create_portfolio_version,
        get_optimizer_run,
        get_portfolio_version,
        initialize_database,
        link_run_result,
        open_database,
    )

    conn = open_database(tmp_path / "versions.sqlite3")
    initialize_database(conn)

    conn.execute("BEGIN")
    run_id = create_optimizer_run(
        conn,
        parent_version_id=None,
        data_source="data/us_public_proxy_returns.csv",
        year_start=1970,
        year_end=2025,
        asset_universe=["USA-LCB", "USA-LTT"],
        objective={"cagr": 1.0},
        constraints={},
        optimizer_config={"population_size": 32},
        random_seed=99,
    )
    version_id = create_portfolio_version(
        conn,
        parent_version_id=None,
        source_run_id=run_id,
        name="tx-root",
        weights={"USA-LCB": 0.5, "USA-LTT": 0.5},
        metrics={"cagr": 0.07},
        notes=None,
    )

    link_run_result(conn, run_id=run_id, version_id=version_id)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO portfolio_versions (
                created_at, name, parent_version_id, source_run_id,
                weights_json, metrics_json, notes
            ) VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)
            """,
            (
                "tx-dup",
                None,
                run_id,
                '{"USA-LCB": 1.0}',
                '{"cagr": 0.01}',
                None,
            ),
        )

    conn.rollback()

    assert get_optimizer_run(conn, run_id) is None
    assert get_portfolio_version(conn, version_id) is None


def test_link_run_result_raises_when_run_row_missing(tmp_path):
    from pcopt.storage import (
        create_optimizer_run,
        create_portfolio_version,
        initialize_database,
        link_run_result,
        open_database,
    )

    conn = open_database(tmp_path / "versions.sqlite3")
    initialize_database(conn)

    existing_run_id = create_optimizer_run(
        conn,
        parent_version_id=None,
        data_source="data/us_public_proxy_returns.csv",
        year_start=1970,
        year_end=2025,
        asset_universe=["USA-LCB", "USA-LTT"],
        objective={"cagr": 1.0},
        constraints={},
        optimizer_config={"population_size": 32},
        random_seed=123,
    )
    existing_version_id = create_portfolio_version(
        conn,
        parent_version_id=None,
        source_run_id=existing_run_id,
        name="existing",
        weights={"USA-LCB": 0.5, "USA-LTT": 0.5},
        metrics={"cagr": 0.07},
        notes=None,
    )

    with pytest.raises(RuntimeError, match="link_run_result"):
        link_run_result(conn, run_id=999_999, version_id=existing_version_id)


def test_cli_version_show_returns_weights_and_metrics(tmp_path):
    from pcopt import cli
    from pcopt.storage import (
        create_optimizer_run,
        create_portfolio_version,
        initialize_database,
        link_run_result,
        open_database,
    )

    db_path = tmp_path / "versions.sqlite3"
    conn = open_database(db_path)
    initialize_database(conn)
    run_id = create_optimizer_run(
        conn,
        parent_version_id=None,
        data_source="data/us_public_proxy_returns.csv",
        year_start=1970,
        year_end=2025,
        asset_universe=["USA-LCB", "USA-LTT"],
        objective={"cagr": 1.0},
        constraints={},
        optimizer_config={"population_size": 32},
        random_seed=7,
    )
    version_id = create_portfolio_version(
        conn,
        parent_version_id=None,
        source_run_id=run_id,
        name="inspect me",
        weights={"USA-LCB": 0.5, "USA-LTT": 0.5},
        metrics={"cagr": 0.07},
        notes=None,
    )
    link_run_result(conn, run_id=run_id, version_id=version_id)
    conn.commit()

    parser = cli.build_parser()
    args = parser.parse_args(["version-show", "--db", str(db_path), "--id", str(version_id)])

    payload = cli.run_version_show(args)

    assert payload["id"] == version_id
    assert payload["weights"]["USA-LCB"] == 0.5
    assert payload["metrics"]["cagr"] == 0.07


def test_cli_version_show_requires_existing_database(tmp_path):
    from pcopt import cli

    db_path = tmp_path / "missing.sqlite3"
    parser = cli.build_parser()
    args = parser.parse_args(["version-show", "--db", str(db_path), "--id", "1"])

    with pytest.raises(FileNotFoundError, match="database does not exist"):
        cli.run_version_show(args)

    assert not db_path.exists()


def test_cli_version_children_returns_only_direct_children(tmp_path):
    from pcopt import cli

    db_path = tmp_path / "versions.sqlite3"
    ids = _create_lineage_fixture(db_path)

    parser = cli.build_parser()
    args = parser.parse_args(["version-children", "--db", str(db_path), "--id", str(ids["root_version_id"])])

    payload = cli.run_version_children(args)

    assert [row["id"] for row in payload] == [ids["child_version_id"]]
    assert payload[0]["parent_version_id"] == ids["root_version_id"]
    assert payload[0]["weights"]["GLO-GLD"] == 0.2


def test_cli_version_roots_returns_versions_without_parents(tmp_path):
    from pcopt import cli

    db_path = tmp_path / "versions.sqlite3"
    ids = _create_lineage_fixture(db_path)

    parser = cli.build_parser()
    args = parser.parse_args(["version-roots", "--db", str(db_path)])

    payload = cli.run_version_roots(args)

    assert [row["id"] for row in payload] == [ids["root_version_id"]]
    assert payload[0]["parent_version_id"] is None
    assert payload[0]["name"] == "root"


def test_cli_run_show_returns_full_run_context(tmp_path):
    from pcopt import cli

    db_path = tmp_path / "versions.sqlite3"
    ids = _create_lineage_fixture(db_path)

    parser = cli.build_parser()
    args = parser.parse_args(["run-show", "--db", str(db_path), "--id", str(ids["child_run_id"])])

    payload = cli.run_run_show(args)

    assert payload["id"] == ids["child_run_id"]
    assert payload["parent_version_id"] == ids["root_version_id"]
    assert payload["result_version_id"] == ids["child_version_id"]
    assert payload["asset_universe"] == ["USA-LCB", "USA-LTT", "GLO-GLD"]
    assert payload["optimizer_config"] == {"population_size": 48}
