"""Runtime environment bootstrap for Vibe-Trading Hermes entrypoints."""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import sys
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
_WORKSPACES_DIR = _REPO_ROOT / "workspaces"
_DEFAULT_WORKSPACE_ID = "public"
_ENV_BOOTSTRAPPED = False
_LOCAL_PLUGIN_BOOTSTRAPPED = False


def get_data_root(workspace_id: str | None = None) -> Path:
    """Return the canonical runtime data root for a workspace.

    Runtime state is stored under ``workspaces/<workspace_id>``.
    When no workspace id is provided, the shared ``public`` workspace is used.
    """
    normalized_workspace_id = (workspace_id or _DEFAULT_WORKSPACE_ID).strip() or _DEFAULT_WORKSPACE_ID
    root = (_WORKSPACES_DIR / normalized_workspace_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_hermes_home() -> Path:
    """Return the active Hermes home used by the backend runtime."""
    hermes_home = _resolve_hermes_home().resolve()
    hermes_home.mkdir(parents=True, exist_ok=True)
    return hermes_home


def _sync_terminal_cwd_env() -> None:
    """Export the canonical data root for Hermes tool compatibility.

    ``TERMINAL_CWD`` is not a user-configurable input anymore; it mirrors the
    deterministic workspace root so Hermes tools that still consult the env var
    stay aligned with runtime storage.
    """
    os.environ["TERMINAL_CWD"] = str(get_data_root())


def get_runs_dir(data_root: Path | None = None) -> Path:
    """Return the canonical run storage directory for the active data root."""
    return (data_root or get_data_root()) / "runs"


def get_sessions_dir(data_root: Path | None = None) -> Path:
    """Return the canonical session storage directory for the active data root."""
    return (data_root or get_data_root()) / "sessions"


def get_uploads_dir(data_root: Path | None = None) -> Path:
    """Return the canonical uploads storage directory for the active data root."""
    return (data_root or get_data_root()) / "uploads"


def get_swarm_root(data_root: Path | None = None) -> Path:
    """Return the canonical swarm storage root for the active data root."""
    return (data_root or get_data_root()) / ".swarm"


def get_swarm_runs_dir(data_root: Path | None = None) -> Path:
    """Return the canonical swarm runs directory for the active data root."""
    return get_swarm_root(data_root) / "runs"


_FALSEY_STRINGS = {"", "0", "false", "off", "no", "none", "disabled"}
_VALID_REASONING_EFFORTS = {"xhigh", "high", "medium", "low", "minimal"}


def _disable_workspace_plugin_paths() -> None:
    """Disable workspace-local Hermes plugin discovery/install flows.

    Vibe-Trading ships application plugins through installed entry points from
    shared repo code. End-user workspaces must not discover or install plugins
    from their workspace-local HERMES_HOME.
    """
    os.environ["HERMES_DISABLE_USER_PLUGINS"] = "1"
    os.environ["HERMES_DISABLE_PROJECT_PLUGINS"] = "1"


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


def _uses_global_openai_base_url(provider: str | None) -> bool:
    """Return whether this provider should inherit OPENAI_BASE_URL semantics."""
    normalized = str(provider or "").strip().lower()
    return normalized in {"", "openai", "azure-openai", "custom"} or normalized.startswith("custom:")


def _clear_stale_openai_base_url(provider: str | None) -> None:
    """Drop OPENAI_BASE_URL for named providers resolved via Hermes runtime config."""
    if _uses_global_openai_base_url(provider):
        return
    os.environ.pop("OPENAI_BASE_URL", None)


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


def _has_vibe_trading_entry_point() -> bool:
    """Return whether the installed environment exposes the Vibe-Trading plugin entry point."""
    try:
        entry_points = importlib.metadata.entry_points()
        if hasattr(entry_points, "select"):
            group = entry_points.select(group="hermes_agent.plugins")
        elif isinstance(entry_points, dict):
            group = entry_points.get("hermes_agent.plugins", [])
        else:
            group = [ep for ep in entry_points if ep.group == "hermes_agent.plugins"]
    except Exception:
        return False
    return any(getattr(ep, "name", "") == "vibe-trading" for ep in group)


def _ensure_local_vibe_trading_plugin() -> None:
    """Register the local Vibe-Trading Hermes plugin when the package is not installed.

    Tests and source-tree runs often execute without installing ``vibe-trading-ai``
    into the active venv, which means Hermes entry-point discovery cannot see the
    ``hermes_agent.plugins`` registration from ``agent/pyproject.toml``. In that
    case we register the same plugin module directly from source so app-owned
    runtime behavior does not depend on editable-install state.
    """
    global _LOCAL_PLUGIN_BOOTSTRAPPED
    if _LOCAL_PLUGIN_BOOTSTRAPPED or _has_vibe_trading_entry_point():
        return

    hermes_root = _REPO_ROOT / "hermes-agent"
    for path in (AGENT_DIR, hermes_root):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)

    try:
        from tools.registry import registry

        if registry.get_entry("setup_backtest_run") is not None:
            _LOCAL_PLUGIN_BOOTSTRAPPED = True
            return

        from hermes_cli.plugins import LoadedPlugin, PluginContext, PluginManifest, get_plugin_manager

        manager = get_plugin_manager()
        module = importlib.import_module("src.plugins.vibe_trading")
        manifest = PluginManifest(
            name="vibe-trading",
            version="source-tree",
            description="Local Vibe-Trading plugin fallback",
            source="project",
            path=str(AGENT_DIR / "src" / "plugins" / "vibe_trading"),
        )
        before_tools = set(manager._plugin_tool_names)
        ctx = PluginContext(manifest, manager)
        module.register(ctx)

        loaded = LoadedPlugin(manifest=manifest, module=module, enabled=True)
        loaded.tools_registered = sorted(manager._plugin_tool_names - before_tools)
        manager._plugins[manifest.name] = loaded
        _LOCAL_PLUGIN_BOOTSTRAPPED = True
    except Exception:
        # Non-fatal fallback: installed entry points or explicit imports may still work.
        pass


def prepare_hermes_project_context(*, chdir: bool = False) -> Path:
    """Prepare repo-root context for Vibe-Trading Hermes entrypoints.

    This helper sets ``VIBE_TRADING_ROOT`` and can optionally ``chdir`` to the
    repository root before importing ``run_agent``. The Vibe-Trading plugin is
    packaged as a Hermes entry-point plugin from ``src.plugins.vibe_trading``,
    so project-plugin env flags and repo-local plugin directories are not
    required for plugin discovery.
    """
    _set_env_if_missing_or_blank("VIBE_TRADING_ROOT", str(_REPO_ROOT))
    _disable_workspace_plugin_paths()
    _ensure_local_vibe_trading_plugin()
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
        if _uses_global_openai_base_url(str(provider or "")):
            _set_env_if_missing_or_blank("OPENAI_BASE_URL", model_cfg.get("base_url"))
        else:
            _clear_stale_openai_base_url(str(provider or ""))
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


def _resolve_primary_runtime_kwargs() -> dict[str, object]:
    """Resolve the main Hermes runtime into explicit AIAgent kwargs.

    Vibe constructs ``AIAgent`` from backend code instead of invoking the
    Hermes CLI entrypoint. Preserve the resolved provider/base URL/API mode so
    the backend agent uses the same runtime that ``config.yaml`` selected.
    """
    requested = (os.getenv("HERMES_INFERENCE_PROVIDER") or "").strip() or None

    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider

        runtime = resolve_runtime_provider(requested=requested)
    except Exception:
        return {}

    if not isinstance(runtime, dict):
        return {}

    kwargs: dict[str, object] = {}
    provider = str(runtime.get("provider") or "").strip()
    api_mode = str(runtime.get("api_mode") or "").strip()
    base_url = str(runtime.get("base_url") or "").strip()
    api_key = str(runtime.get("api_key") or "").strip()

    if provider:
        kwargs["provider"] = provider
    if api_mode:
        kwargs["api_mode"] = api_mode
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key

    return kwargs


def ensure_runtime_env() -> None:
    """Load the repo-local Hermes config and bridge it into runtime env vars."""
    global _ENV_BOOTSTRAPPED
    if _ENV_BOOTSTRAPPED:
        return

    prepare_hermes_project_context(chdir=False)
    _sync_terminal_cwd_env()
    config = _load_hermes_config()
    _seed_env_from_hermes_config(config)
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

    model_cfg = config.get("model") if isinstance(config, dict) else None
    provider = model_cfg.get("provider") if isinstance(model_cfg, dict) else None
    _clear_stale_openai_base_url(str(provider or ""))

    _bridge_hermes_env_to_langchain_defaults()
    backend_python = _resolve_backend_python()
    if backend_python.exists():
        _set_env_if_missing_or_blank("VIBE_TRADING_PYTHON", str(backend_python))
        _set_env_if_missing_or_blank("VIBE_TRADING_PIP", f"{backend_python} -m pip")
    _ENV_BOOTSTRAPPED = True


def get_hermes_agent_kwargs() -> dict[str, object]:
    """Build optional AIAgent kwargs from runtime env settings."""
    ensure_runtime_env()

    kwargs: dict[str, object] = _resolve_primary_runtime_kwargs()

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
