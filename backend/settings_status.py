"""Readiness / setup status for Settings + soft onboarding (DEC-034)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .catalog_editor import catalog_meta_summary, list_catalog_models
from .catalog_refresh import validate_frozen_config
from .config import INDEX_MANIFEST_PATH, OPENROUTER_API_KEY, SEMANTIC_BACKEND
from .dependencies import load_runtime_settings
from .frozen_config.loader import ARENA_CONFIG_PATH, MODEL_CATALOG_PATH

VALID_SQUAD_POLICIES = frozenset({"quorum", "require_all"})
DEFAULT_SQUAD_POLICY = "quorum"

# Hot fields: apply on next turn / next index without process restart.
HOT_FIELD_META: Dict[str, Dict[str, str]] = {
    "arena_models": {"apply": "hot", "section": "squad"},
    "chairman_model": {"apply": "hot", "section": "squad"},
    "arena_squad": {"apply": "hot", "section": "squad"},
    "squad_policy": {"apply": "hot", "section": "squad"},
    "theme": {"apply": "hot", "section": "appearance"},
    "repo_root": {
        "apply": "hot",
        "section": "repository",
        "note": "Applies to next retrieval/index operations",
    },
}


def normalize_squad_policy(value: Any) -> str:
    """Return a valid squad_policy; default quorum for missing/invalid."""
    if value is None:
        return DEFAULT_SQUAD_POLICY
    text = str(value).strip().casefold()
    if text in VALID_SQUAD_POLICIES:
        return text
    return DEFAULT_SQUAD_POLICY


def _check(
    check_id: str,
    *,
    ok: bool,
    severity: str,
    label: str,
    detail: str,
    fix: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "ok": ok,
        "severity": severity,
        "label": label,
        "detail": detail,
        "fix": fix,
    }


def _openrouter_check() -> Dict[str, Any]:
    present = bool(OPENROUTER_API_KEY and str(OPENROUTER_API_KEY).strip())
    return _check(
        "openrouter_key",
        ok=present,
        severity="error",
        label="OpenRouter API key",
        detail="Present in process environment"
        if present
        else "Missing — set OPENROUTER_API_KEY in .env and restart the API",
        fix="secrets" if not present else None,
    )


def _squad_check(settings: Dict[str, Any]) -> Dict[str, Any]:
    models = [m for m in (settings.get("arena_models") or []) if m]
    chair = (settings.get("chairman_model") or "").strip()
    squad = settings.get("arena_squad") or "—"
    ok = bool(models) and bool(chair)
    detail = (
        f"{squad} · {len(models)} arena model(s) · chair {chair}"
        if ok
        else "No arena models or chairman configured"
    )
    return _check(
        "squad",
        ok=ok,
        severity="error",
        label="Arena squad",
        detail=detail,
        fix="squad" if not ok else None,
    )


def _catalog_validate_check() -> tuple[Dict[str, Any], bool, List[str]]:
    ok, issues = validate_frozen_config()
    detail = "arena_config.yaml and model_catalog.yaml validate"
    if not ok:
        detail = "; ".join(issues[:3]) or "Validation failed"
        if len(issues) > 3:
            detail += f" (+{len(issues) - 3} more)"
    check = _check(
        "catalog_validate",
        ok=ok,
        severity="error",
        label="Catalog config",
        detail=detail,
        fix="catalog" if not ok else None,
    )
    return check, ok, issues


def _squad_in_catalog_check(settings: Dict[str, Any]) -> Dict[str, Any]:
    models = [m for m in (settings.get("arena_models") or []) if m]
    chair = (settings.get("chairman_model") or "").strip()
    needed = list(dict.fromkeys([*models, chair] if chair else models))
    if not needed:
        return _check(
            "squad_in_catalog",
            ok=False,
            severity="warning",
            label="Squad models in catalog",
            detail="No models to check",
            fix="squad",
        )
    try:
        catalog = list_catalog_models()
        known = set((catalog.get("models") or {}).keys())
    except Exception as exc:
        return _check(
            "squad_in_catalog",
            ok=False,
            severity="warning",
            label="Squad models in catalog",
            detail=f"Could not read catalog: {exc}",
            fix="catalog",
        )
    missing = [m for m in needed if m not in known]
    ok = not missing
    detail = (
        "All configured models are in model_catalog.yaml"
        if ok
        else f"Missing from catalog: {', '.join(missing[:5])}"
        + (f" (+{len(missing) - 5} more)" if len(missing) > 5 else "")
    )
    return _check(
        "squad_in_catalog",
        ok=ok,
        severity="warning",
        label="Squad models in catalog",
        detail=detail,
        fix="catalog" if not ok else None,
    )


def _repo_root_check(settings: Dict[str, Any]) -> Dict[str, Any]:
    raw = settings.get("repo_root") or "."
    path = Path(str(raw)).expanduser()
    try:
        resolved = path.resolve()
        ok = resolved.is_dir()
        detail = str(resolved) if ok else f"Not a directory: {resolved}"
    except Exception as exc:
        ok = False
        detail = f"Invalid path: {exc}"
    return _check(
        "repo_root",
        ok=ok,
        severity="warning",
        label="Repository root",
        detail=detail,
        fix="repository" if not ok else None,
    )


def _index_check() -> Dict[str, Any]:
    path = Path(INDEX_MANIFEST_PATH)
    if not path.is_file():
        return _check(
            "index_manifest",
            ok=False,
            severity="warning",
            label="Index manifest",
            detail=f"No manifest at {path} — index a repository when ready",
            fix="repository",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _check(
            "index_manifest",
            ok=False,
            severity="warning",
            label="Index manifest",
            detail=f"Unreadable manifest: {exc}",
            fix="repository",
        )
    chunk_count = data.get("chunk_count")
    if chunk_count is None and isinstance(data.get("files"), dict):
        chunk_count = sum(
            int(v.get("chunks", 0) or 0)
            for v in data["files"].values()
            if isinstance(v, dict)
        )
    detail_parts = [f"Present at {path}"]
    if chunk_count is not None:
        detail_parts.append(f"{chunk_count} chunks")
    indexed_at = data.get("indexed_at") or data.get("updated_at") or data.get("created_at")
    if indexed_at:
        detail_parts.append(f"updated {indexed_at}")
    return _check(
        "index_manifest",
        ok=True,
        severity="info",
        label="Index manifest",
        detail=" · ".join(detail_parts),
        fix=None,
    )


def _secrets_block() -> Dict[str, Any]:
    """Presence-only secrets view; write shape reserved (DEF-014)."""
    key_present = bool(OPENROUTER_API_KEY and str(OPENROUTER_API_KEY).strip())
    return {
        "openrouter_api_key": {
            "present": key_present,
            "writable": False,
            "write_supported": False,
            "hint": "Set OPENROUTER_API_KEY in .env and restart the API process.",
        },
        "semantic_backend": {
            "value": SEMANTIC_BACKEND,
            "present": True,
            "writable": False,
            "write_supported": False,
            "hint": "Configured via SEMANTIC_BACKEND env (default colbert).",
        },
    }


def build_settings_status() -> Dict[str, Any]:
    """Aggregate readiness for Settings UI and soft onboarding banner."""
    settings = load_runtime_settings()
    settings = {
        **settings,
        "squad_policy": normalize_squad_policy(settings.get("squad_policy")),
    }

    checks: List[Dict[str, Any]] = [
        _openrouter_check(),
        _squad_check(settings),
    ]
    cat_check, _, issues = _catalog_validate_check()
    checks.append(cat_check)
    checks.append(_squad_in_catalog_check(settings))
    checks.append(_repo_root_check(settings))
    checks.append(_index_check())

    # ready = all error-severity checks pass (warnings don't block "ready enough")
    error_checks = [c for c in checks if c["severity"] == "error"]
    ready = all(c["ok"] for c in error_checks)
    ready_count = sum(1 for c in checks if c["ok"])
    total = len(checks)

    meta = catalog_meta_summary()

    return {
        "ready": ready,
        "score": {"ready": ready_count, "total": total},
        "checks": checks,
        "settings": {
            k: settings.get(k)
            for k in (
                "arena_models",
                "chairman_model",
                "arena_squad",
                "squad_policy",
                "theme",
                "repo_root",
            )
        },
        "available_squads": settings.get("available_squads") or [],
        "field_meta": HOT_FIELD_META,
        "freeze": {
            "arena_config_path": str(ARENA_CONFIG_PATH),
            "catalog_config_path": str(MODEL_CATALOG_PATH),
            "catalog_meta": meta,
            "validate_ok": cat_check["ok"],
            "validate_issues": issues,
            "requires_restart_hint": (
                "Restart the API process to apply FREEZE YAML / catalog changes."
            ),
        },
        "secrets": _secrets_block(),
        "onboarding": {
            "hard_gate": False,
            "banner_when_not_ready": True,
        },
    }
