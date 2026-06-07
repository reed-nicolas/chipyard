# Data Infrastructure — Recent Updates

Summary of updates for group meeting presentation.

---

## 1. VCS Simulator Support

**What:** Data collection now works for **both Verilator and VCS** simulations.

**How it works:**
- The `log_data_post_run` hook lives in `common.mk`, which is included by both `sims/verilator/Makefile` and `sims/vcs/Makefile`
- Each simulator sets `sim_name` (`verilator` or `vcs`), which is passed to `log_data.py` as `--simulator`
- Runs are stored in the DB with `simulator` and `run_target` columns so you can filter by simulator

**Covered targets:**
- `run-binary`, `run-binary-fast`
- `run-asm-tests`, `run-bmark-tests`

**Usage:** Same as Verilator — no extra setup. VCS runs are logged when `DATACOLL=on` or when `enable_data_collection` is on in config.

---

## 2. Vector Datastore (RAG / Semantic Search)

**What:** Optional vector index for semantic search over runs.

**Components:**
- **`vec_runs` table** — sqlite-vec virtual table storing 384-dimensional embeddings per run
- **`util/datacoll/embeddings.py`** — `embed_text()` and `build_run_chunk()` using sentence-transformers
- **`util/backfill_vec_runs.py`** — backfill embeddings for runs logged before `enable_vector_index` was enabled

**Config (`.chipyard/config.json`):**
```json
{
  "enable_vector_index": "on",
  "embedding_model": "all-MiniLM-L6-v2"
}
```

**Dependencies:**
- `pip install sqlite-vec sentence-transformers`
- Python must support `enable_load_extension` (some system Pythons do not — use `CHIPYARD_PYTHON=/path/to/conda/bin/python` if needed)

**Flow:**
1. After each run, `log_data.py` builds a text chunk (config, benchmark, cycles, metrics, log excerpt)
2. Chunk is embedded with the chosen model
3. Embedding is stored in `vec_runs` linked to `runs.id`

**Querying:** Use `datacoll.db.connection_with_vec(db_path)` as the connection factory when querying `vec_runs` (sqlite3 CLI cannot load the extension).

**Backfill:** For runs logged before `enable_vector_index` was on:
```bash
python3 util/backfill_vec_runs.py
```

---

## 3. Schema Additions

- **`runs.run_target`** — Make target (e.g. `run-binary`, `run-asm-tests`)
- **`runs.simulator`** — `verilator` or `vcs` (from `sim_name`)

---

## Quick Reference

| Feature | Status |
|---------|--------|
| Verilator logging | ✅ |
| VCS logging | ✅ |
| Vector index (RAG) | ✅ Optional (config + deps) |
| Backfill existing runs | ✅ `util/backfill_vec_runs.py` |
