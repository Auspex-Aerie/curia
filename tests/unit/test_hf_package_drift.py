"""Keep published HF package sources aligned with runtime defaults."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_LABELS = ROOT / "backend" / "rag" / "router_training.json"
MIRROR_LABELS = ROOT / "hf" / "curia-router-labels" / "data" / "router_training.json"
STACK_DEFAULTS = ROOT / "hf" / "curia-grounding-config" / "stack.defaults.json"


def test_router_labels_mirror_matches_canonical():
    assert CANONICAL_LABELS.is_file(), "canonical router labels missing"
    assert MIRROR_LABELS.is_file(), "HF mirror of router labels missing"
    assert (
        CANONICAL_LABELS.read_bytes() == MIRROR_LABELS.read_bytes()
    ), "hf/curia-router-labels/data/router_training.json drifted from backend/rag/router_training.json — re-copy or run publish sync"


def test_stack_defaults_match_runtime_config():
    import re

    from backend import config

    # Avoid importing backend.rag (heavy optional deps); pin revision from source.
    rerank_src = (ROOT / "backend" / "rag" / "rerank.py").read_text(encoding="utf-8")
    match = re.search(r'JINA_V3_REVISION\s*=\s*"([^"]+)"', rerank_src)
    assert match, "JINA_V3_REVISION not found in backend/rag/rerank.py"
    jina_revision = match.group(1)

    assert STACK_DEFAULTS.is_file()
    stack = json.loads(STACK_DEFAULTS.read_text(encoding="utf-8"))

    assert stack["semantic"]["backend"] == config.SEMANTIC_BACKEND
    assert stack["semantic"]["colbert_learned"] is config.COLBERT_LEARNED
    assert stack["semantic"]["model"] == config.COLBERT_MODEL
    assert stack["semantic"]["device"] == config.COLBERT_DEVICE

    assert stack["router"]["mode"] == config.QUERY_ROUTER
    assert stack["router"]["embed_model"] == config.ROUTER_EMBED_MODEL

    assert stack["fusion"]["mode"] == config.FUSION_MODE
    assert stack["graph"]["mode"] == config.GRAPH_MODE

    assert stack["rerank"]["enabled"] is config.RERANK_ENABLED
    assert stack["rerank"]["model"] == config.RERANK_MODEL
    assert stack["rerank"]["revision"] == jina_revision

    assert stack["retrieval"]["retrieve_candidates"] == config.RETRIEVE_CANDIDATES
    assert stack["retrieval"]["rerank_top_k"] == config.RERANK_TOP_K
    assert stack["retrieval"]["context_chunk_cap"] == config.CONTEXT_CHUNK_CAP
