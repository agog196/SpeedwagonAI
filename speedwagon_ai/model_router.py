from __future__ import annotations

import os
from dataclasses import dataclass

from speedwagon_ai.config import Settings


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str
    tier: str
    reason: str


def choose_model(settings: Settings, operation: str) -> ModelChoice:
    """Choose a cost-aware model without changing the public settings contract."""
    normalized = operation.strip().lower().replace("-", "_")
    default = settings.openai_model.strip() or "gpt-4.1-mini"
    cheap = configured_model("SPEEDWAGON_MODEL_CHEAP", default)
    strong = configured_model("SPEEDWAGON_MODEL_STRONG", default)
    command = configured_model("SPEEDWAGON_MODEL_COMMAND", cheap)
    vision = configured_model("SPEEDWAGON_MODEL_VISION", strong)
    web = configured_model("SPEEDWAGON_MODEL_WEB", strong)

    if normalized == "command_parse":
        return ModelChoice(settings.llm_provider, command, "low", "command parsing uses the cheapest configured structured model")
    if normalized == "vision_context":
        return ModelChoice(settings.llm_provider, vision, "medium", "screenshot understanding needs a vision-capable model")
    if normalized in {"email", "email_draft", "extraction", "relationship_inference", "task_cleanup"}:
        return ModelChoice(settings.llm_provider, cheap, "cheap", f"{normalized} is a routine batched workflow")
    if normalized in {"web_search", "fresh_context"}:
        return ModelChoice(settings.llm_provider, web, "high", f"{normalized} may need fresher or broader context")
    if normalized == "deep_synthesis":
        return ModelChoice(settings.llm_provider, strong, "high", f"{normalized} may need deeper synthesis")
    return ModelChoice(settings.llm_provider, strong, "medium", f"{normalized} may need deeper synthesis")


def configured_model(name: str, fallback: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return fallback.strip() or "gpt-4.1-mini"
    return value.strip()


def web_search_enabled() -> bool:
    return os.getenv("SPEEDWAGON_ENABLE_WEB_SEARCH", "false").strip().lower() in {"1", "true", "yes", "on"}


def cost_label(choice: ModelChoice) -> str:
    if choice.tier in {"cheap", "low"}:
        return "low"
    if choice.tier == "high":
        return "high"
    return "medium"
