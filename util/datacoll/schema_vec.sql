-- Vector/RAG schema for Chipyard datastore (optional, requires sqlite-vec)
-- Applied only when enable_vector_index is on and sqlite-vec is installed.
-- Links run_id to runs.id for JOINs. Users query via SQL; LLMs use semantic search.

-- vec0 virtual table: run_id primary key, embedding, +content auxiliary
-- Embedding dimension must match the model (e.g. 384 for all-MiniLM-L6-v2)
-- NOTE: This file is executed via Python after loading sqlite_vec extension.
-- The extension must be loaded before CREATE VIRTUAL TABLE.

CREATE VIRTUAL TABLE IF NOT EXISTS vec_runs USING vec0(
  run_id INTEGER PRIMARY KEY,
  embedding FLOAT[384],
  +content TEXT
);
