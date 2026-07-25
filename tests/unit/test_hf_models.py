"""HuggingFace RAG model registry (no network in unit tests)."""

from backend.rag.hf_models import configure_hf_cache, rag_model_specs


def test_rag_model_specs_include_core_roles():
    specs = rag_model_specs()
    roles = {s.role for s in specs}
    assert roles == {"colbert", "rerank", "router_embed"}
    by_role = {s.role: s for s in specs}
    assert "colbert" in by_role["colbert"].model_id or "/" in by_role["colbert"].model_id
    assert by_role["rerank"].kind in {"transformers", "sentence_transformers"}


def test_configure_hf_cache_sets_env(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("CURIA_HF_HOME", raising=False)
    root = tmp_path / "hf"
    resolved = configure_hf_cache(str(root))
    assert resolved == str(root)
    assert root.is_dir()
    import os

    assert os.environ["HF_HOME"] == str(root)
