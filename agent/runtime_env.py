"""Runtime environment bootstrap for Vibe-Trading Hermes entrypoints."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except ImportError:
    pass

AGENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = AGENT_DIR.parent
_DEFAULT_HERMES_HOME = AGENT_DIR / ".hermes"
_ENV_BOOTSTRAPPED = False


def get_data_root() -> Path:
    """Return the user-scoped data root derived from TERMINAL_CWD.

    A relative TERMINAL_CWD is resolved against AGENT_DIR (e.g. 'chris' →
    agent/chris/).  Falls back to AGENT_DIR when the variable is unset.
    The directory is created on first call.
    """
    _raw = os.getenv("TERMINAL_CWD", "").strip()
    if _raw and not os.path.isabs(_raw):
        root = (AGENT_DIR / _raw).resolve()
    elif _raw:
        root = Path(_raw).resolve()
    else:
        root = AGENT_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root
_FALSEY_STRINGS = {"", "0", "false", "off", "no", "none", "disabled"}
_VALID_REASONING_EFFORTS = {"xhigh", "high", "medium", "low", "minimal"}


def _set_env_if_missing_or_blank(name: str, value: str | None) -> None:
    """Populate an environment variable when it is missing or blank."""
    if value is None:
        return
    normalized = str(value).strip().strip('"').strip("'")
    if not normalized:
        return
    current = os.getenv(name)
    if current is None or not current.strip():
        os.environ[name] = normalized


def _resolve_hermes_home() -> Path:
    """Return the repo-local Hermes home path used by the agent runtime."""
    configured = (os.getenv("HERMES_HOME") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_HERMES_HOME


def _resolve_backend_python() -> Path:
    """Return the preferred agent-local Python interpreter path."""
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return AGENT_DIR / ".venv" / scripts_dir / executable


def prepare_hermes_project_context(*, chdir: bool = False) -> Path:
    """Prepare cwd/env so Hermes can discover repo-local project plugins.

    Hermes project plugins are resolved from ``Path.cwd() / ".hermes/plugins"``.
    Vibe-Trading keeps its Hermes plugin at the repository root, so callers that
    launch from ``agent/`` must opt into the repo root working directory before
    importing ``run_agent``.
    """
    _set_env_if_missing_or_blank("VIBE_TRADING_ROOT", str(_REPO_ROOT))
    _set_env_if_missing_or_blank("HERMES_ENABLE_PROJECT_PLUGINS", "true")
    if chdir:
        os.chdir(_REPO_ROOT)
    return _REPO_ROOT



def _load_hermes_config() -> dict[str, Any]:
    """Load `config.yaml` from the repo-local Hermes home."""
    hermes_home = _resolve_hermes_home()
    _set_env_if_missing_or_blank("HERMES_HOME", str(hermes_home))
    _set_env_if_missing_or_blank("VIBE_TRADING_ROOT", str(_REPO_ROOT))

    config_path = hermes_home / "config.yaml"
    if yaml is None or not config_path.exists():
        return {}

    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}



def _normalize_azure_openai_base_url(endpoint: str) -> str:
    """Normalize Azure endpoints to the OpenAI-compatible `/openai/v1` form."""
    normalized = (endpoint or "").strip().strip('"').strip("'").rstrip("/")
    if not normalized:
        return ""
    lower = normalized.lower()
    if "/openai/deployments/" in lower or "/openai/v1" in lower:
        return normalized
    if lower.endswith("/openai"):
        return normalized + "/v1"
    return normalized + "/openai/v1"



def _seed_env_from_hermes_config(config: dict[str, Any]) -> None:
    """Expose repo-local Hermes config values through the process environment."""
    if not config:
        return

    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        provider = model_cfg.get("provider")
        default_model = model_cfg.get("default") or model_cfg.get("model")
        _set_env_if_missing_or_blank("HERMES_INFERENCE_PROVIDER", provider)
        _set_env_if_missing_or_blank("HERMES_MODEL", default_model)
        _set_env_if_missing_or_blank("OPENAI_BASE_URL", model_cfg.get("base_url"))
        _set_env_if_missing_or_blank("OPENAI_API_KEY", model_cfg.get("api_key"))
        _set_env_if_missing_or_blank("HERMES_MAX_OUTPUT_TOKENS", model_cfg.get("max_tokens"))
        _set_env_if_missing_or_blank("HERMES_CONTEXT_WINDOW", model_cfg.get("context_length"))
        if provider:
            _set_env_if_missing_or_blank(
                "LANGCHAIN_PROVIDER",
                "azure" if str(provider).strip().lower() == "azure-openai" else provider,
            )
        if default_model:
            _set_env_if_missing_or_blank("LANGCHAIN_MODEL_NAME", default_model)

    agent_cfg = config.get("agent")
    if isinstance(agent_cfg, dict):
        _set_env_if_missing_or_blank("HERMES_REASONING_EFFORT", agent_cfg.get("reasoning_effort"))

    vibe_cfg = config.get("vibe_trading")
    if not isinstance(vibe_cfg, dict):
        return

    azure_cfg = vibe_cfg.get("azure_openai")
    if isinstance(azure_cfg, dict):
        endpoint = azure_cfg.get("endpoint")
        deployment = azure_cfg.get("deployment_name")
        api_version = azure_cfg.get("api_version")
        azure_api_key = azure_cfg.get("api_key")
        normalized_base = _normalize_azure_openai_base_url(str(endpoint or ""))

        _set_env_if_missing_or_blank("AZURE_OPENAI_ENDPOINT", endpoint)
        _set_env_if_missing_or_blank("AZURE_OPENAI_DEPLOYMENT_NAME", deployment)
        _set_env_if_missing_or_blank("AZURE_OPENAI_API_VERSION", api_version)
        _set_env_if_missing_or_blank(
            "AZURE_OPENAI_API_KEY",
            azure_api_key or (model_cfg.get("api_key") if isinstance(model_cfg, dict) else None),
        )
        if normalized_base:
            _set_env_if_missing_or_blank("OPENAI_BASE_URL", normalized_base)

    kimi_cfg = vibe_cfg.get("kimi")
    if isinstance(kimi_cfg, dict):
        _set_env_if_missing_or_blank("KIMI_API_KEY", kimi_cfg.get("api_key"))
        _set_env_if_missing_or_blank("KIMI_BASE_URL", kimi_cfg.get("base_url"))
        _set_env_if_missing_or_blank("KIMI_USER_AGENT", kimi_cfg.get("user_agent"))

    data_cfg = vibe_cfg.get("data_providers")
    if isinstance(data_cfg, dict):
        _set_env_if_missing_or_blank("TUSHARE_TOKEN", data_cfg.get("tushare_token"))

    runtime_cfg = vibe_cfg.get("runtime")
    if isinstance(runtime_cfg, dict):
        _set_env_if_missing_or_blank("TIMEOUT_SECONDS", runtime_cfg.get("timeout_seconds"))
        _set_env_if_missing_or_blank("MAX_RETRIES", runtime_cfg.get("max_retries"))


def _bridge_azure_env_to_hermes_defaults() -> None:
    """Expose Azure settings through the Hermes/OpenAI-compatible env aliases."""
    azure_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    azure_endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip()
    azure_deployment = (os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") or "").strip()
    normalized_base = _normalize_azure_openai_base_url(azure_endpoint)

    if azure_key and normalized_base:
        _set_env_if_missing_or_blank("HERMES_INFERENCE_PROVIDER", "azure-openai")
        _set_env_if_missing_or_blank("OPENAI_API_KEY", azure_key)
        _set_env_if_missing_or_blank("OPENAI_BASE_URL", normalized_base)
        _set_env_if_missing_or_blank("LANGCHAIN_PROVIDER", "azure")

    if azure_deployment:
        _set_env_if_missing_or_blank("HERMES_MODEL", azure_deployment)
        _set_env_if_missing_or_blank("LANGCHAIN_MODEL_NAME", azure_deployment)


def _bridge_hermes_env_to_langchain_defaults() -> None:
    """Keep legacy LangChain env names aligned with Hermes runtime settings."""
    provider = (os.getenv("HERMES_INFERENCE_PROVIDER") or "").strip().lower()
    model = (os.getenv("HERMES_MODEL") or "").strip()

    if provider:
        _set_env_if_missing_or_blank(
            "LANGCHAIN_PROVIDER",
            "azure" if provider == "azure-openai" else provider,
        )
    if model:
        _set_env_if_missing_or_blank("LANGCHAIN_MODEL_NAME", model)


def _positive_int_from_env(*names: str) -> int | None:
    """Return the first positive integer found in the given env vars."""
    for name in names:
        raw = os.getenv(name, "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return None


def _cap_max_tokens_for_provider(max_tokens: int) -> int:
    """Clamp provider-specific output token defaults to avoid known API 400s."""
    provider = (os.getenv("HERMES_INFERENCE_PROVIDER") or "").strip().lower()
    if provider == "azure-openai":
        azure_cap = _positive_int_from_env("AZURE_OPENAI_MAX_OUTPUT_TOKENS") or 4096
        return min(max_tokens, azure_cap)
    return max_tokens


def ensure_runtime_env() -> None:
    """Load the repo-local Hermes config and bridge it into runtime env vars."""
    global _ENV_BOOTSTRAPPED
    if _ENV_BOOTSTRAPPED:
        return

    prepare_hermes_project_context(chdir=False)
    _seed_env_from_hermes_config(_load_hermes_config())
    _bridge_azure_env_to_hermes_defaults()

    kimi_key = os.getenv("KIMI_API_KEY", "")
    if kimi_key:
        _set_env_if_missing_or_blank("HERMES_INFERENCE_PROVIDER", "kimi-coding")
        _set_env_if_missing_or_blank("HERMES_MODEL", "kimi-for-coding")
        _set_env_if_missing_or_blank("KIMI_USER_AGENT", "RooCode/1.0.0")
        _set_env_if_missing_or_blank(
            "HERMES_REASONING_EFFORT",
            os.getenv("KIMI_REASONING_EFFORT", "medium"),
        )
        _set_env_if_missing_or_blank(
            "HERMES_MAX_OUTPUT_TOKENS",
            os.getenv("KIMI_MAX_OUTPUT_TOKENS", "32768"),
        )
        _set_env_if_missing_or_blank(
            "HERMES_CONTEXT_WINDOW",
            os.getenv("KIMI_CONTEXT_WINDOW", "262144"),
        )
        if kimi_key.startswith("sk-kimi-"):
            _set_env_if_missing_or_blank("KIMI_BASE_URL", "https://api.kimi.com/coding/v1")

    _bridge_hermes_env_to_langchain_defaults()
    backend_python = _resolve_backend_python()
    if backend_python.exists():
        _set_env_if_missing_or_blank("VIBE_TRADING_PYTHON", str(backend_python))
        _set_env_if_missing_or_blank("VIBE_TRADING_PIP", f"{backend_python} -m pip")
    _ENV_BOOTSTRAPPED = True


def get_hermes_agent_kwargs() -> dict[str, object]:
    """Build optional AIAgent kwargs from runtime env settings."""
    ensure_runtime_env()

    kwargs: dict[str, object] = {}

    max_tokens = _positive_int_from_env(
        "HERMES_MAX_OUTPUT_TOKENS",
        "KIMI_MAX_OUTPUT_TOKENS",
    )
    if max_tokens is not None:
        kwargs["max_tokens"] = _cap_max_tokens_for_provider(max_tokens)

    effort = (
        os.getenv("HERMES_REASONING_EFFORT")
        or os.getenv("KIMI_REASONING_EFFORT")
        or ""
    ).strip().lower()
    if effort and effort not in _FALSEY_STRINGS and effort in _VALID_REASONING_EFFORTS:
        kwargs["reasoning_config"] = {"enabled": True, "effort": effort}
    elif effort and effort in _FALSEY_STRINGS:
        kwargs["reasoning_config"] = {"enabled": False}

    return kwargs
