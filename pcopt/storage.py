import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_database(path: str | Path) -> sqlite3.Connection:
    return _configure_connection(sqlite3.connect(Path(path)))


def open_database_readonly(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    if not db_path.exists():
        raise FileNotFoundError(f"database does not exist: {db_path}")
    return _configure_connection(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True))


def initialize_database(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS optimizer_runs (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            parent_version_id INTEGER NULL REFERENCES portfolio_versions(id),
            data_source TEXT NOT NULL,
            year_start INTEGER NULL,
            year_end INTEGER NULL,
            asset_universe_json TEXT NOT NULL,
            objective_json TEXT NOT NULL,
            constraints_json TEXT NOT NULL,
            optimizer_config_json TEXT NOT NULL,
            random_seed INTEGER NULL,
            result_version_id INTEGER NULL UNIQUE REFERENCES portfolio_versions(id)
        );
        CREATE TABLE IF NOT EXISTS portfolio_versions (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            name TEXT NULL,
            parent_version_id INTEGER NULL REFERENCES portfolio_versions(id),
            source_run_id INTEGER NULL UNIQUE REFERENCES optimizer_runs(id),
            weights_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            notes TEXT NULL
        );
        """
    )
    version_row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    if version_row is None:
        conn.execute("INSERT INTO schema_meta(key, value) VALUES ('schema_version', '1')")
    elif version_row[0] != "1":
        raise RuntimeError(f"Unsupported schema version: {version_row[0]}")
    conn.commit()


def create_optimizer_run(
    conn: sqlite3.Connection,
    *,
    parent_version_id,
    data_source,
    year_start,
    year_end,
    asset_universe,
    objective,
    constraints,
    optimizer_config,
    random_seed,
) -> int:
    row = conn.execute(
        """
        INSERT INTO optimizer_runs (
            created_at, parent_version_id, data_source, year_start, year_end,
            asset_universe_json, objective_json, constraints_json,
            optimizer_config_json, random_seed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            parent_version_id,
            data_source,
            year_start,
            year_end,
            json.dumps(asset_universe, sort_keys=True),
            json.dumps(objective, sort_keys=True),
            json.dumps(constraints, sort_keys=True),
            json.dumps(optimizer_config, sort_keys=True),
            random_seed,
        ),
    )
    return int(row.lastrowid)


def create_portfolio_version(
    conn: sqlite3.Connection,
    *,
    parent_version_id,
    source_run_id,
    name,
    weights,
    metrics,
    notes,
) -> int:
    row = conn.execute(
        """
        INSERT INTO portfolio_versions (
            created_at, name, parent_version_id, source_run_id,
            weights_json, metrics_json, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            name,
            parent_version_id,
            source_run_id,
            json.dumps(weights, sort_keys=True),
            json.dumps(metrics, sort_keys=True),
            notes,
        ),
    )
    return int(row.lastrowid)


def link_run_result(conn: sqlite3.Connection, *, run_id, version_id) -> None:
    run_update = conn.execute(
        "UPDATE optimizer_runs SET result_version_id = ? WHERE id = ?",
        (version_id, run_id),
    )
    if run_update.rowcount != 1:
        raise RuntimeError(f"link_run_result failed to link optimizer_runs row for run_id={run_id}")

    version_update = conn.execute(
        "UPDATE portfolio_versions SET source_run_id = ? WHERE id = ?",
        (run_id, version_id),
    )
    if version_update.rowcount != 1:
        raise RuntimeError(f"link_run_result failed to link portfolio_versions row for version_id={version_id}")


def get_portfolio_version(conn: sqlite3.Connection, version_id: int):
    row = conn.execute("SELECT * FROM portfolio_versions WHERE id = ?", (version_id,)).fetchone()
    return _decode_portfolio_version_row(row)


def list_child_versions(conn: sqlite3.Connection, parent_version_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM portfolio_versions WHERE parent_version_id = ? ORDER BY id",
        (parent_version_id,),
    ).fetchall()
    return [_decode_portfolio_version_row(row) for row in rows]


def list_root_versions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM portfolio_versions WHERE parent_version_id IS NULL ORDER BY id").fetchall()
    return [_decode_portfolio_version_row(row) for row in rows]


def get_optimizer_run(conn: sqlite3.Connection, run_id: int):
    row = conn.execute("SELECT * FROM optimizer_runs WHERE id = ?", (run_id,)).fetchone()
    return _decode_optimizer_run_row(row)


def _decode_portfolio_version_row(row):
    if row is None:
        return None
    out = dict(row)
    out["weights"] = json.loads(out.pop("weights_json"))
    out["metrics"] = json.loads(out.pop("metrics_json"))
    return out


def _decode_optimizer_run_row(row):
    if row is None:
        return None
    out = dict(row)
    out["asset_universe"] = json.loads(out.pop("asset_universe_json"))
    out["objective"] = json.loads(out.pop("objective_json"))
    out["constraints"] = json.loads(out.pop("constraints_json"))
    out["optimizer_config"] = json.loads(out.pop("optimizer_config_json"))
    return out
