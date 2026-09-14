"""Provider configuration for models exposing Chat Completions."""

import os
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictInt


class LLMBackendParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backend: Literal["openai", "openrouter", "ollama"]
    model: str = Field(min_length=1)
    base_url: HttpUrl | None = None
    temperature: float | None = Field(default=0, ge=0, le=2)
    max_output_tokens: Annotated[StrictInt, Field(ge=16, le=32768)] = 256
    timeout_seconds: float = Field(default=60, gt=0, le=600)
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None


def connection(params: LLMBackendParams) -> dict:
    endpoints = {
        "openai": "https://api.openai.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "ollama": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    }
    if params.backend == "ollama":
        key = "ollama"
    else:
        variable = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}[params.backend]
        key = os.getenv(variable)
        if not key or key.strip().lower() in {"replace-me", "your-key-here"}:
            raise ValueError(f"Set {variable} in the environment or repository-root .env")
    return {"api_key": key, "base_url": str(params.base_url or endpoints[params.backend]),
            "timeout": params.timeout_seconds, "max_retries": 1}


def generation_options(params: LLMBackendParams) -> dict:
    options = {"model": params.model}
    token_field = "max_completion_tokens" if params.backend == "openai" else "max_tokens"
    options[token_field] = params.max_output_tokens
    if params.temperature is not None:
        options["temperature"] = params.temperature
    if params.reasoning_effort is not None:
        options["reasoning_effort"] = params.reasoning_effort
    if params.backend == "openrouter":
        options["extra_body"] = {"provider": {"require_parameters": True}}
    return options
