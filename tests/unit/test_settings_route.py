"""Settings + setup status API (DEC-034)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    settings_path = tmp_path / "config.json"
    monkeypatch.setattr("backend.dependencies.SETTINGS_PATH", settings_path)
    return settings_path


def test_read_settings_includes_squad_policy(client, isolated_settings):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["squad_policy"] == "quorum"
    assert "arena_models" in data
    assert "available_squads" in data


def test_update_squad_policy_persists(client, isolated_settings):
    resp = client.post("/api/settings", json={"squad_policy": "require_all"})
    assert resp.status_code == 200
    assert resp.json()["squad_policy"] == "require_all"
    raw = json.loads(isolated_settings.read_text(encoding="utf-8"))
    assert raw["squad_policy"] == "require_all"
    assert client.get("/api/settings").json()["squad_policy"] == "require_all"


def test_invalid_squad_policy_normalized_on_save(client, isolated_settings):
    # Pydantic rejects non-literal before save
    resp = client.post("/api/settings", json={"squad_policy": "maybe"})
    assert resp.status_code == 422


def test_custom_arena_models(client, isolated_settings):
    models = ["meta-llama/llama-3.3-70b-instruct:free", "qwen/qwen3-coder:free"]
    resp = client.post(
        "/api/settings",
        json={
            "arena_models": models,
            "chairman_model": "qwen/qwen3-coder:free",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["arena_models"] == models
    assert data["chairman_model"] == "qwen/qwen3-coder:free"
    assert data["arena_squad"] == "custom"


def test_settings_status_shape(client, isolated_settings, monkeypatch):
    monkeypatch.setattr("backend.settings_status.OPENROUTER_API_KEY", "test-key")
    resp = client.get("/api/settings/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "ready" in data
    assert data["score"]["total"] >= 1
    assert isinstance(data["checks"], list)
    ids = {c["id"] for c in data["checks"]}
    assert "openrouter_key" in ids
    assert "squad" in ids
    assert "catalog_validate" in ids
    assert data["onboarding"]["hard_gate"] is False
    assert data["secrets"]["openrouter_api_key"]["present"] is True
    assert data["secrets"]["openrouter_api_key"]["write_supported"] is False
    assert data["settings"]["squad_policy"] == "quorum"
    assert "field_meta" in data


def test_settings_status_openrouter_missing(client, isolated_settings, monkeypatch):
    monkeypatch.setattr("backend.settings_status.OPENROUTER_API_KEY", None)
    data = client.get("/api/settings/status").json()
    key_check = next(c for c in data["checks"] if c["id"] == "openrouter_key")
    assert key_check["ok"] is False
    assert data["ready"] is False
    assert data["secrets"]["openrouter_api_key"]["present"] is False


def test_secret_write_not_implemented(client):
    resp = client.post(
        "/api/settings/secrets",
        json={"name": "openrouter_api_key", "value": "sk-test"},
    )
    assert resp.status_code == 501
    detail = resp.json()["detail"]
    assert detail["write_supported"] is False


def test_repo_root_check(client, isolated_settings, tmp_path, monkeypatch):
    monkeypatch.setattr("backend.settings_status.OPENROUTER_API_KEY", "k")
    good = tmp_path / "repo"
    good.mkdir()
    client.post("/api/settings", json={"repo_root": str(good)})
    data = client.get("/api/settings/status").json()
    repo_check = next(c for c in data["checks"] if c["id"] == "repo_root")
    assert repo_check["ok"] is True

    client.post("/api/settings", json={"repo_root": str(tmp_path / "missing")})
    data = client.get("/api/settings/status").json()
    repo_check = next(c for c in data["checks"] if c["id"] == "repo_root")
    assert repo_check["ok"] is False
