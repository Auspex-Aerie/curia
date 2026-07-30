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
import sys
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, TextIO

logger = logging.getLogger(__name__)

# Public model ids — keep in sync with config defaults / load sites.
COLBERT_HF_ID = os.getenv("COLBERT_MODEL", "colbert-ir/colbertv2.0")
RERANK_HF_ID = os.getenv("RERANK_MODEL", "jinaai/jina-reranker-v3")
ROUTER_EMBED_HF_ID = os.getenv(
    "ROUTER_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
# Keep in lockstep with backend.rag.rerank.JINA_V3_REVISION (runtime loader).
from .rerank import JINA_V3_REVISION  # noqa: E402

# Approximate Hub download sizes (weights + tokenizer; not torch itself).
# Operators see multi-minute silence otherwise and assume the CLI is stuck.
SIZE_HINTS = {
    "colbert": "~400–500 MB",
    "rerank": "~1.0–1.3 GB",
    "router_embed": "~80–100 MB",
}
# Runtime dependency installed via uv (not part of prefetch). Future lighter stacks
# may shrink this; today CodeRAG cold start still needs a full torch wheel.
TORCH_SIZE_HINT = "~1.5–2+ GB (via `uv sync`, not this CLI)"


@dataclass(frozen=True)
class RagModelSpec:
    """One downloadable retrieval dependency."""

    role: str
    model_id: str
    kind: str  # colbert | transformers | sentence_transformers
    revision: Optional[str] = None
    trust_remote_code: bool = False

    @property
    def size_hint(self) -> str:
        return SIZE_HINTS.get(self.role, "varies")


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


def hf_token_present() -> bool:
    """True when a Hub token is available (env or huggingface-cli login cache)."""
    if os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN"):
        return True
    try:
        from huggingface_hub import get_token

        return bool(get_token())
    except Exception:
        return False


def configure_hf_cache(cache_dir: Optional[str] = None) -> Optional[str]:
    """Point HuggingFace caches at ``CURIA_HF_HOME`` or an explicit path.

    When ``cache_dir`` is passed (CLI ``--cache-dir``), it **overrides** any
    inherited HF cache env vars so the download lands where the operator asked.
    When only ``CURIA_HF_HOME`` is set, fill missing HF vars without clobbering
    an already-configured ``HF_HOME``.
    Returns the resolved cache root, or None when using the library default.
    """
    explicit = cache_dir is not None
    resolved = cache_dir or os.getenv("CURIA_HF_HOME") or os.getenv("HF_HOME")
    if not resolved:
        return None
    path = os.path.expanduser(resolved)
    os.makedirs(path, exist_ok=True)
    hub = os.path.join(path, "hub")
    transformers = os.path.join(path, "transformers")
    st = os.path.join(path, "sentence-transformers")
    if explicit:
        os.environ["HF_HOME"] = path
        os.environ["HUGGINGFACE_HUB_CACHE"] = hub
        os.environ["TRANSFORMERS_CACHE"] = transformers
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = st
    elif os.getenv("CURIA_HF_HOME"):
        os.environ.setdefault("HF_HOME", path)
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", hub)
        os.environ.setdefault("TRANSFORMERS_CACHE", transformers)
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", st)
    return path


def _enable_hub_progress() -> None:
    """Encourage HF hub / transformers progress bars on TTY."""
    os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    try:
        from huggingface_hub.utils import enable_progress_bars

        enable_progress_bars()
    except Exception:
        pass


def _prefetch_one(spec: RagModelSpec) -> None:
    logger.info(
        "Prefetching RAG model role=%s id=%s kind=%s (~%s)",
        spec.role,
        spec.model_id,
        spec.kind,
        spec.size_hint,
    )
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
    progress: Optional[TextIO] = None,
) -> List[str]:
    """Download configured RAG weights into the HF cache. Returns model ids."""
    out = progress if progress is not None else sys.stdout
    configure_hf_cache(cache_dir)
    _enable_hub_progress()
    selected = list(specs) if specs is not None else rag_model_specs()
    downloaded: List[str] = []
    total = len(selected)
    for i, spec in enumerate(selected, start=1):
        print(
            f"[{i}/{total}] Starting {spec.role}: {spec.model_id}  ({spec.size_hint})",
            file=out,
            flush=True,
        )
        t0 = time.monotonic()
        _prefetch_one(spec)
        elapsed = time.monotonic() - t0
        downloaded.append(spec.model_id)
        print(
            f"[{i}/{total}] Ready     {spec.role}: {spec.model_id}  ({elapsed:.1f}s)",
            file=out,
            flush=True,
        )
        logger.info("Ready: %s (%s) in %.1fs", spec.model_id, spec.role, elapsed)
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

    print("Curia RAG prefetch (Hugging Face Hub → local cache, not Git LFS)")
    print()
    if hf_token_present():
        print("HF token: present (better rate limits)")
    else:
        print(
            "HF token: not set — anonymous Hub downloads are allowed for these "
            "public models but often very slow."
        )
        print(
            "  Recommend a free read token: https://huggingface.co/settings/tokens"
        )
        print("  then:  export HF_TOKEN=hf_...   # or HUGGING_FACE_HUB_TOKEN")
    print()
    print("Models (approx. download size; already-cached files are reused):")
    for spec in specs:
        rev = f" @ {spec.revision[:12]}…" if spec.revision else ""
        print(f"  - {spec.role:12} {spec.model_id}{rev}  ({spec.size_hint})")
    print()
    print(f"Also required (installed by uv, not this CLI): PyTorch {TORCH_SIZE_HINT}")
    print(
        "  A future thinner stack may shrink the torch footprint; today full CUDA/CPU "
        "wheels still come with `uv sync`."
    )
    cache = configure_hf_cache(args.cache_dir)
    if cache:
        print(f"Cache root: {cache}")
    else:
        print("Cache root: Hugging Face default (~/.cache/huggingface)")
    print()
    print("Progress: per-model start/end lines below; Hub may also print download bars.")
    print("Long quiet stretches usually mean a multi-GB transfer is in flight.")
    print()

    try:
        done = prefetch_rag_models(specs, cache_dir=args.cache_dir, progress=sys.stdout)
    except Exception as exc:
        logger.exception("Prefetch failed")
        print(f"ERROR: {exc}")
        if not hf_token_present():
            print(
                "Hint: set HF_TOKEN (free HF account, read scope) and retry if "
                "you hit rate limits or stalls."
            )
        return 1
    print()
    print(f"Done. {len(done)} model(s) ready in the local HF cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
