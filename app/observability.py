from __future__ import annotations

import os
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, TypeVar

from langsmith import traceable

F = TypeVar("F", bound=Callable[..., Any])
LANGSMITH_ENV_KEYS = {
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_PROJECT",
    "LANGCHAIN_ENDPOINT",
}


def _read_project_env(env_file: str | Path = ".env") -> Dict[str, str]:
    path = Path(env_file)
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key in LANGSMITH_ENV_KEYS:
            values[key] = value.strip().strip('"').strip("'")
    return values


def _enabled_value(value: str | None, default: str = "false") -> bool:
    return (value or default).lower() in {"1", "true", "yes", "on"}


def _langsmith_config() -> Dict[str, str]:
    file_values = _read_project_env()
    config = dict(file_values)
    for key in LANGSMITH_ENV_KEYS:
        if os.environ.get(key):
            config[key] = os.environ[key]
    return config


def _sync_langsmith_env_when_usable(config: Dict[str, str]) -> None:
    key = config.get("LANGSMITH_API_KEY") or config.get("LANGCHAIN_API_KEY")
    if not key:
        # Critical: do not export LANGSMITH_TRACING=true without a key, because
        # LangGraph/LangSmith auto-instrumentation will try to send anonymous
        # traces and spam 401 errors during tests/local runs.
        return
    for env_key, value in config.items():
        if value:
            os.environ.setdefault(env_key, value)


def langsmith_enabled() -> bool:
    """Only trace when explicitly enabled and an API key is configured."""
    config = _langsmith_config()
    tracing_enabled = _enabled_value(config.get("LANGSMITH_TRACING")) or _enabled_value(config.get("LANGCHAIN_TRACING_V2"))
    has_key = bool(config.get("LANGSMITH_API_KEY") or config.get("LANGCHAIN_API_KEY"))
    if tracing_enabled and has_key:
        _sync_langsmith_env_when_usable(config)
        return True
    return False


def traceable_if_configured(*, name: str, run_type: str = "chain") -> Callable[[F], F]:
    """LangSmith decorator that becomes a no-op without credentials."""
    def decorator(fn: F) -> F:
        if langsmith_enabled():
            return traceable(name=name, run_type=run_type)(fn)  # type: ignore[return-value]

        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
