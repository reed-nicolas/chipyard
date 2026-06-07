"""
Embedding utilities for RAG/vector indexing of Chipyard run data.
Uses sentence-transformers when available; gracefully degrades when not installed.
"""

from __future__ import annotations

from typing import Any

# Default model: 384 dimensions, good balance of quality and size
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIM = 384

_model_cache: Any = None


def _get_model(model_name: str):
    """Lazy-load sentence-transformers model. Returns None if not installed."""
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    try:
        from sentence_transformers import SentenceTransformer

        _model_cache = SentenceTransformer(model_name)
        return _model_cache
    except ImportError:
        return None


def embed_text(text: str, model_name: str = DEFAULT_EMBEDDING_MODEL) -> list[float] | None:
    """
    Embed a single text string. Returns list of floats or None if embedding unavailable.
    """
    model = _get_model(model_name)
    if model is None:
        return None
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def build_run_chunk(
    *,
    config: str,
    benchmark: str,
    commit_hash: str,
    simulator: str | None = None,
    run_target: str | None = None,
    cycles: int | None = None,
    instructions: int | None = None,
    ipc: float | None = None,
    metrics_json: str = "{}",
    log_snippet: str | None = None,
) -> str:
    """
    Build a text chunk suitable for embedding. LLM-friendly summary of a run.
    """
    parts = [
        f"Chipyard simulation run: config={config}, benchmark={benchmark}.",
        f"Git commit: {commit_hash}.",
    ]
    if run_target:
        parts.append(f"Run target: {run_target}.")
    if simulator:
        parts.append(f"Simulator: {simulator}.")
    if cycles is not None:
        parts.append(f"Cycles: {cycles}.")
    if instructions is not None:
        parts.append(f"Instructions: {instructions}.")
    if ipc is not None:
        parts.append(f"IPC: {ipc:.4f}.")
    if metrics_json and metrics_json != "{}":
        try:
            import json

            m = json.loads(metrics_json)
            if m:
                metrics_str = ", ".join(f"{k}={v}" for k, v in list(m.items())[:10])
                parts.append(f"Metrics: {metrics_str}.")
        except (json.JSONDecodeError, TypeError):
            pass
    if log_snippet:
        # First ~500 chars of log for context
        snippet = log_snippet[:500].replace("\n", " ").strip()
        if snippet:
            parts.append(f"Log excerpt: {snippet}")
    return " ".join(parts)


def embedding_available() -> bool:
    """Return True if sentence-transformers is installed and usable."""
    return _get_model(DEFAULT_EMBEDDING_MODEL) is not None
