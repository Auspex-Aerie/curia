"""Runtime settings, squad presets, and setup status (DEC-034)."""

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..dependencies import apply_squad_preset, load_runtime_settings, save_runtime_settings
from ..settings_status import (
    DEFAULT_SQUAD_POLICY,
    VALID_SQUAD_POLICIES,
    build_settings_status,
    normalize_squad_policy,
)
from ..squad_presets import list_squad_summaries

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    arena_models: Optional[list[str]] = None
    chairman_model: Optional[str] = None
    arena_squad: Optional[str] = None
    squad_policy: Optional[Literal["quorum", "require_all"]] = None
    theme: Optional[Literal["light", "dark"]] = None
    repo_root: Optional[str] = None

    @field_validator("arena_models")
    @classmethod
    def _nonempty_models(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        cleaned = [m.strip() for m in value if m and str(m).strip()]
        if not cleaned:
            raise ValueError("arena_models must contain at least one model id")
        return cleaned

    @field_validator("chairman_model", "repo_root")
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("must be a non-empty string")
        return text


class SecretWriteRequest(BaseModel):
    """Reserved shape for future secret write (DEF-014). Not implemented."""

    name: str = Field(..., description="Secret id, e.g. openrouter_api_key")
    value: str = Field(..., min_length=1)


@router.get("")
async def read_settings() -> dict[str, Any]:
    return load_runtime_settings()


@router.post("")
async def update_settings(payload: SettingsUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    if "squad_policy" in data:
        data["squad_policy"] = normalize_squad_policy(data["squad_policy"])
        if data["squad_policy"] not in VALID_SQUAD_POLICIES:
            raise HTTPException(status_code=400, detail="Invalid squad_policy")
    # Custom composition: if models/chair set without squad name, mark custom.
    if (
        ("arena_models" in data or "chairman_model" in data)
        and "arena_squad" not in data
        and data.get("arena_models") is not None
    ):
        data.setdefault("arena_squad", "custom")
    return save_runtime_settings(data)


@router.get("/status")
async def settings_status() -> dict[str, Any]:
    """Soft readiness report for onboarding banner and Setup tab."""
    return build_settings_status()


@router.get("/squads")
async def list_squads() -> dict[str, Any]:
    return {"squads": list_squad_summaries()}


@router.post("/squad/{squad_name}")
async def select_squad(squad_name: str) -> dict[str, Any]:
    try:
        return apply_squad_preset(squad_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/secrets")
async def write_secret(_payload: SecretWriteRequest) -> dict[str, Any]:
    """Placeholder for future secret write (DEF-014). Always 501 for now."""
    raise HTTPException(
        status_code=501,
        detail={
            "error": "secret_write_not_supported",
            "write_supported": False,
            "hint": (
                "Set secrets in .env (e.g. OPENROUTER_API_KEY) and restart the API. "
                "UI secret write is deferred (DEF-014)."
            ),
            "default_squad_policy": DEFAULT_SQUAD_POLICY,
        },
    )
