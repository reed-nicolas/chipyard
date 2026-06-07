"""DB init, schema creation, insert_build, insert_run, get_or_create_build_id.
Vector/RAG support via sqlite-vec when enable_vector_index is on."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
_SCHEMA_VEC_PATH = Path(__file__).resolve().parent / "schema_vec.sql"
VEC_EMBEDDING_DIM = 384  # Must match schema_vec.sql and embedding model


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create DB file and directory if missing. Does not apply schema."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


def connection_with_vec(db_path: str | Path) -> sqlite3.Connection:
    """
    Return a DB connection with sqlite-vec extension loaded.
    Use for Ray Data read_sql connection_factory when querying vec_runs:
        ray.data.read_sql("SELECT * FROM vec_runs WHERE ...", lambda: connection_with_vec(db_path))
    """
    conn = init_db(db_path)
    load_vec_extension(conn)
    return conn


def load_vec_extension(conn: sqlite3.Connection) -> bool:
    """Load sqlite-vec extension. Returns True on success, False if not installed."""
    try:
        conn.execute("SELECT vec_version()").fetchone()
        return True  # Already loaded
    except (sqlite3.OperationalError, Exception):
        pass
    try:
        conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except (ImportError, Exception):
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass
        return False


def apply_vec_schema(conn: sqlite3.Connection) -> bool:
    """Apply vec0 schema. Requires sqlite-vec loaded. Returns True on success."""
    if not load_vec_extension(conn):
        return False
    try:
        sql = _SCHEMA_VEC_PATH.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.commit()
        return True
    except Exception:
        return False


def apply_schema(conn: sqlite3.Connection) -> None:
    """Apply schema.sql idempotently."""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()
    _migrate_add_columns(conn)


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Add new columns to existing runs table if missing."""
    for col, ctype in [("run_dir", "TEXT"), ("simulator", "TEXT"), ("github_user", "TEXT"), ("run_target", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {ctype}")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column" not in str(e).lower():
                raise


def get_or_create_build_id(
    conn: sqlite3.Connection,
    commit_hash: str,
    config: str,
    branch: str | None,
    remote_url: str | None,
    is_dirty: bool,
    build_path: str | None,
    user: str | None,
    host: str | None,
) -> int | None:
    """Get existing build id or insert new row. Returns None if builds table not used."""
    cur = conn.execute(
        "SELECT id FROM builds WHERE commit_hash=? AND config=?",
        (commit_hash, config),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        """INSERT INTO builds (commit_hash, branch, remote_url, is_dirty, config, build_path, user, host)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            commit_hash,
            branch or "",
            remote_url or "",
            1 if is_dirty else 0,
            config,
            build_path or "",
            user or "",
            host or "",
        ),
    )
    conn.commit()
    return cur.lastrowid


def insert_run(
    conn: sqlite3.Connection,
    *,
    build_id: int | None = None,
    commit_hash: str,
    branch: str | None,
    remote_url: str | None,
    is_dirty: bool,
    config: str,
    benchmark: str | None,
    cycles: int | None = None,
    instructions: int | None = None,
    ipc: float | None = None,
    cpi: float | None = None,
    metrics: str = "{}",
    log_path: str | None,
    run_dir: str | None = None,
    simulator: str | None = None,
    github_user: str | None = None,
    run_target: str | None = None,
    user: str | None,
    host: str | None,
) -> int:
    """Insert a row into runs. Returns the run id (lastrowid)."""
    cur = conn.execute(
        """INSERT INTO runs (
            build_id, commit_hash, branch, remote_url, is_dirty, config,
            benchmark, cycles, instructions, ipc, cpi, metrics, log_path, run_dir, simulator, github_user, run_target, user, host
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            build_id,
            commit_hash,
            branch or "",
            remote_url or "",
            1 if is_dirty else 0,
            config,
            benchmark or "",
            cycles,
            instructions,
            ipc,
            cpi,
            metrics,
            log_path or "",
            run_dir or "",
            simulator or "",
            github_user or "",
            run_target or "",
            user or "",
            host or "",
        ),
    )
    conn.commit()
    return cur.lastrowid


def insert_run_embedding(
    conn: sqlite3.Connection,
    run_id: int,
    content: str,
    embedding: list[float],
) -> bool:
    """
    Insert a run embedding into vec_runs. Requires sqlite-vec loaded.
    Returns True on success, False if vec extension unavailable or failed.
    """
    if not load_vec_extension(conn):
        return False
    if len(embedding) != VEC_EMBEDDING_DIM:
        return False
    try:
        import json

        # vec0 accepts JSON array for float vectors
        vec_json = json.dumps(embedding)
        conn.execute(
            "INSERT INTO vec_runs (run_id, embedding, content) VALUES (?, ?, ?)",
            (run_id, vec_json, content),
        )
        conn.commit()
        return True
    except Exception:
        return False
