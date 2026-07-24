"""Pydantic schemas for arena_config.yaml and model_catalog.yaml."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True)


class ContextBudgetConfig(BaseModel):
    model_config = _FROZEN

    safety_margin: float = 0.85
    output_token_allowance: int = 4000
    default_registered_limit: int = 131072
    context_chunk_cap: int = 60


class SummarizerConfig(BaseModel):
    model_config = _FROZEN

    model: Optional[str] = None
    concurrency: Optional[int] = None
    chairman_fallback: bool = True


class CatalogPolicyConfig(BaseModel):
    model_config = _FROZEN

    refresh_ttl_hours: int = 168
    observation_delta_threshold: float = 0.10
    observation_ttl_days: int = 60


class SquadGateConfig(BaseModel):
    """Soft-confirm thresholds for MCP/agent full turns (DEC-030 follow-up).

    A turn requires confirmation when either limit is exceeded. Interactive
    Observatory streams bypass the gate entirely (``enforce_gate=False``).
    """

    model_config = _FROZEN

    # Gate when projected model-call count exceeds this (all models).
    call_threshold: int = 12
    # Gate when projected *paid* model-call count exceeds this (per-role
    # attribution: each answer/ranking/draft/… call by a paid model counts 1).
    # Defaults high enough that a single paid chair on a free arena does not
    # alone force confirm; a fully paid cheap_pros council (9 calls) still does.
    paid_call_threshold: int = 4


class ArenaConfig(BaseModel):
    model_config = _FROZEN

    version: int = 1
    context: ContextBudgetConfig = Field(default_factory=ContextBudgetConfig)
    summarizer: SummarizerConfig = Field(default_factory=SummarizerConfig)
    catalog: CatalogPolicyConfig = Field(default_factory=CatalogPolicyConfig)
    tag_modifiers: Dict[str, float] = Field(default_factory=lambda: {"free": 0.25})
    squad_gate: SquadGateConfig = Field(default_factory=SquadGateConfig)


class ModelEntry(BaseModel):
    model_config = _FROZEN

    tags: List[str] = Field(default_factory=list)
    registered_limit: Optional[int] = None
    observed_limit: Optional[int] = None
    observed_accepted_at: Optional[str] = None
    model_modifier: float = 1.0
    manual_override_limit: Optional[int] = None
    provenance: str = "manual"


class ModelCatalog(BaseModel):
    model_config = _FROZEN

    version: int = 1
    models: Dict[str, ModelEntry] = Field(default_factory=dict)


class FrozenSnapshot(BaseModel):
    """Immutable config snapshot for the current process."""

    model_config = _FROZEN

    arena: ArenaConfig
    catalog: ModelCatalog
    generation: int
    arena_config_path: str
    catalog_config_path: str