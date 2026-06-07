#!/usr/bin/env python3
"""
Backfill vec_runs with embeddings for runs that were logged before enable_vector_index was on.
Run from chipyard root: python3 util/backfill_vec_runs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from datacoll.config import resolve_config
from datacoll.db import apply_schema, apply_vec_schema, init_db, insert_run_embedding, load_vec_extension
from datacoll.embeddings import build_run_chunk, embed_text


def main() -> int:
    chipyard_root = Path.cwd()
    cfg = resolve_config(None, chipyard_root)
    db_path = cfg["db_path"]
    model = str(cfg.get("embedding_model", "all-MiniLM-L6-v2"))

    if str(cfg.get("enable_vector_index", "off")).lower() != "on":
        print("[backfill] enable_vector_index is off in config; run anyway for backfill.")

    conn = init_db(db_path)
    apply_schema(conn)  # Ensure migrations (e.g. run_target) are applied
    if not load_vec_extension(conn):
        print("[backfill] sqlite-vec not available. Install: pip install sqlite-vec")
        conn.close()
        return 1

    apply_vec_schema(conn)

    # Runs that don't have a vec_runs row
    missing = conn.execute(
        """
        SELECT r.id, r.config, r.benchmark, r.commit_hash, r.simulator, r.run_target,
               r.cycles, r.instructions, r.ipc, r.metrics, r.log_path
        FROM runs r
        LEFT JOIN vec_runs v ON v.run_id = r.id
        WHERE v.run_id IS NULL
        ORDER BY r.id
        """
    ).fetchall()

    if not missing:
        print("[backfill] All runs already in vec_runs. Nothing to do.")
        conn.close()
        return 0

    if not embed_text("test"):
        print("[backfill] sentence-transformers not available. Install: pip install sentence-transformers")
        conn.close()
        return 1

    print(f"[backfill] Embedding {len(missing)} runs...")
    ok = 0
    err = 0
    for row in missing:
        run_id, config, benchmark, commit_hash, simulator, run_target, cycles, instructions, ipc, metrics, log_path = row
        log_snippet = None
        if log_path:
            p = Path(log_path)
            if p.exists():
                try:
                    log_snippet = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass

        content = build_run_chunk(
            config=config or "",
            benchmark=benchmark or "",
            commit_hash=commit_hash or "unknown",
            simulator=simulator,
            run_target=run_target,
            cycles=cycles,
            instructions=instructions,
            ipc=ipc,
            metrics_json=metrics or "{}",
            log_snippet=log_snippet,
        )
        embedding = embed_text(content, model_name=model)
        if embedding and insert_run_embedding(conn, run_id=run_id, content=content, embedding=embedding):
            ok += 1
        else:
            err += 1

    conn.close()
    print(f"[backfill] Done. Inserted {ok}, failed {err}.")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
