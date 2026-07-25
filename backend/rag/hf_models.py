"""HuggingFace model registry and prefetch for Curia's local retrieval stack.

Retrieval weights (ColBERT, reranker, query-router backbone) are **not** stored
in git or Git LFS. They are ordinary HuggingFace Hub models, downloaded on first
use into the standard HF cache (override with ``HF_HOME`` / ``CURIA_HF_HOME``).

This module:
  * documents the exact model IDs Curia expects,
  * optionally points the HF cache at ``CURIA_HF_HOME`` before any download,
  * provides ``prefetch_rag_models()`` so operators can pull weights before the
    first grounded query (avoid multi-GB cold-start mid-turn).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Public model ids — keep in sync with config defaults / load sites.
COLBERT_HF_ID = os.getenv("COLBERT_MODEL", "colbert-ir/colbertv2.0")
RERANK_HF_ID = os.getenv("RERANK_MODEL", "jinaai/jina-reranker-v3")
ROUTER_EMBED_HF_ID = os.getenv(
    "ROUTER_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
JINA_V3_REVISION = "fddc7b54c1577668c67eeaba36f959eb55181736"


@dataclass(frozen=True)
class RagModelSpec:
    """One downloadable retrieval dependency."""

    role: str
    model_id: str
    kind: str  # colbert | transformers | sentence_transformers
    revision: Optional[str] = None
    trust_remote_code: bool = False


def rag_model_specs(
    *,
    colbert: bool = True,
    rerank: bool = True,
    router: bool = True,
) -> List[RagModelSpec]:
    specs: List[RagModelSpec] = []
    if colbert:
        specs.append(
            RagModelSpec(role="colbert", model_id=COLBERT_HF_ID, kind="colbert")
        )
    if rerank:
        trust = "jina" in RERANK_HF_ID.lower()
        specs.append(
            RagModelSpec(
                role="rerank",
                model_id=RERANK_HF_ID,
                kind="transformers" if trust else "sentence_transformers",
                revision=JINA_V3_REVISION if trust else None,
                trust_remote_code=trust,
            )
        )
    if router:
        specs.append(
            RagModelSpec(
                role="router_embed",
                model_id=ROUTER_EMBED_HF_ID,
                kind="sentence_transformers",
            )
        )
    return specs


def configure_hf_cache(cache_dir: Optional[str] = None) -> Optional[str]:
    """Point HuggingFace caches at ``CURIA_HF_HOME`` or an explicit path.

    Sets ``HF_HOME`` (and legacy transformer/hub vars) when a Curia-owned cache
    directory is configured and ``HF_HOME`` is not already set by the operator.
    Returns the resolved cache root, or None when using the library default.
    """
    resolved = cache_dir or os.getenv("CURIA_HF_HOME") or os.getenv("HF_HOME")
    if not resolved:
        return None
    path = os.path.expanduser(resolved)
    os.makedirs(path, exist_ok=True)
    # Only set if operator has not already fixed HF_HOME in the environment
    # before import — still force CURIA_HF_HOME when explicitly provided.
    if cache_dir or os.getenv("CURIA_HF_HOME"):
        os.environ.setdefault("HF_HOME", path)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(path, "hub"))
        os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(path, "transformers"))
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(path, "sentence-transformers"))
    return path


def _prefetch_one(spec: RagModelSpec) -> None:
    logger.info("Prefetching RAG model role=%s id=%s kind=%s", spec.role, spec.model_id, spec.kind)
    if spec.kind == "colbert":
        from pylate import models

        from ..config import get_colbert_device

        models.ColBERT(
            model_name_or_path=spec.model_id,
            device=get_colbert_device(),
        )
        return
    if spec.kind == "transformers":
        from transformers import AutoModel, AutoTokenizer

        kwargs = {"trust_remote_code": spec.trust_remote_code}
        if spec.revision:
            kwargs["revision"] = spec.revision
        AutoTokenizer.from_pretrained(spec.model_id, **kwargs)
        AutoModel.from_pretrained(spec.model_id, **kwargs)
        return
    if spec.kind == "sentence_transformers":
        from sentence_transformers import CrossEncoder, SentenceTransformer

        # CrossEncoder for non-jina rerankers; SentenceTransformer for router.
        if spec.role == "rerank":
            CrossEncoder(spec.model_id, trust_remote_code=spec.trust_remote_code)
        else:
            SentenceTransformer(spec.model_id)
        return
    raise ValueError(f"unknown RAG model kind {spec.kind!r}")


def prefetch_rag_models(
    specs: Optional[Sequence[RagModelSpec]] = None,
    *,
    cache_dir: Optional[str] = None,
) -> List[str]:
    """Download configured RAG weights into the HF cache. Returns model ids."""
    configure_hf_cache(cache_dir)
    selected = list(specs) if specs is not None else rag_model_specs()
    downloaded: List[str] = []
    for spec in selected:
        _prefetch_one(spec)
        downloaded.append(spec.model_id)
        logger.info("Ready: %s (%s)", spec.model_id, spec.role)
    return downloaded


def main(argv: Optional[Iterable[str]] = None) -> int:
    """CLI: ``uv run curia-prefetch-rag``."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Download Curia retrieval models from HuggingFace into the local "
            "cache (not Git LFS). Use before first grounded query to avoid "
            "multi-GB cold starts mid-turn."
        )
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Override cache root (sets HF_HOME). Default: CURIA_HF_HOME or HF default.",
    )
    parser.add_argument("--skip-colbert", action="store_true")
    parser.add_argument("--skip-rerank", action="store_true")
    parser.add_argument("--skip-router", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    specs = rag_model_specs(
        colbert=not args.skip_colbert,
        rerank=not args.skip_rerank,
        router=not args.skip_router,
    )
    print("Prefetching:")
    for spec in specs:
        print(f"  - {spec.role}: {spec.model_id}")
    try:
        done = prefetch_rag_models(specs, cache_dir=args.cache_dir)
    except Exception as exc:
        logger.exception("Prefetch failed")
        print(f"ERROR: {exc}")
        return 1
    print(f"Done. {len(done)} model(s) cached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
