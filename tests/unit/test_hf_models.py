"""HuggingFace RAG model registry (no network in unit tests)."""

from backend.rag.hf_models import (
    SIZE_HINTS,
    TORCH_SIZE_HINT,
    configure_hf_cache,
    hf_token_present,
    rag_model_specs,
)


def test_rag_model_specs_include_core_roles():
    specs = rag_model_specs()
    roles = {s.role for s in specs}
    assert roles == {"colbert", "rerank", "router_embed"}
    by_role = {s.role: s for s in specs}
    assert "colbert" in by_role["colbert"].model_id or "/" in by_role["colbert"].model_id
    assert by_role["rerank"].kind in {"transformers", "sentence_transformers"}
    for spec in specs:
        assert spec.size_hint
        assert spec.role in SIZE_HINTS
    assert "GB" in TORCH_SIZE_HINT


def test_hf_token_present_reads_env(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGING_FACE_HUB_TOKEN", raising=False)
    monkeypatch.setenv("HF_TOKEN", "hf_test_not_real")
    assert hf_token_present() is True


def test_configure_hf_cache_sets_env(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("CURIA_HF_HOME", raising=False)
    root = tmp_path / "hf"
    resolved = configure_hf_cache(str(root))
    assert resolved == str(root)
    assert root.is_dir()
    import os

    assert os.environ["HF_HOME"] == str(root)


def test_configure_hf_cache_explicit_overrides_existing(tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("HF_HOME", "/old/cache")
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", "/old/hub")
    root = tmp_path / "forced"
    configure_hf_cache(str(root))
    assert os.environ["HF_HOME"] == str(root)
    assert os.environ["HUGGINGFACE_HUB_CACHE"] == str(root / "hub")


def test_jina_revision_matches_runtime_loader():
    from backend.rag.hf_models import JINA_V3_REVISION
    from backend.rag.rerank import JINA_V3_REVISION as RUNTIME

    assert JINA_V3_REVISION == RUNTIME
