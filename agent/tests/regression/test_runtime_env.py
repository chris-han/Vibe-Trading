from __future__ import annotations

import os
import sys
import types

import runtime_env
import api_server



def test_ensure_runtime_env_bridges_hermes_config_without_dotenv(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir(parents=True)
    (hermes_home / "config.yaml").write_text(
        """
model:
  provider: azure-openai
  default: gpt-4o
  base_url: https://example-resource.openai.azure.com/openai/v1
  api_key: test-azure-key
  max_tokens: 4096
  context_length: 128000

agent:
  reasoning_effort: medium

vibe_trading:
  azure_openai:
    endpoint: https://example-resource.openai.azure.com/
    deployment_name: gpt-4o
    api_version: 2025-01-01-preview

  data_providers:
    tushare_token: test-tushare-token

  runtime:
    timeout_seconds: 2400
    max_retries: 5
""".strip()
        + "\n",
        encoding="utf-8",
    )

    for key in (
        "HERMES_HOME",
        "HERMES_INFERENCE_PROVIDER",
        "HERMES_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "LANGCHAIN_PROVIDER",
        "LANGCHAIN_MODEL_NAME",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT_NAME",
        "AZURE_OPENAI_API_VERSION",
        "HERMES_MAX_OUTPUT_TOKENS",
        "HERMES_CONTEXT_WINDOW",
        "HERMES_REASONING_EFFORT",
        "TUSHARE_TOKEN",
        "TIMEOUT_SECONDS",
        "MAX_RETRIES",
        "KIMI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setattr(runtime_env, "_ENV_BOOTSTRAPPED", False)

    runtime_env.ensure_runtime_env()

    assert os.getenv("HERMES_HOME") == str(hermes_home)
    assert os.getenv("HERMES_INFERENCE_PROVIDER") == "azure-openai"
    assert os.getenv("HERMES_MODEL") == "gpt-4o"
    assert os.getenv("OPENAI_API_KEY") == "test-azure-key"
    assert os.getenv("OPENAI_BASE_URL") == "https://example-resource.openai.azure.com/openai/v1"
    assert os.getenv("LANGCHAIN_PROVIDER") == "azure"
    assert os.getenv("LANGCHAIN_MODEL_NAME") == "gpt-4o"
    assert os.getenv("AZURE_OPENAI_API_KEY") == "test-azure-key"
    assert os.getenv("AZURE_OPENAI_ENDPOINT") == "https://example-resource.openai.azure.com/"
    assert os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") == "gpt-4o"
    assert os.getenv("AZURE_OPENAI_API_VERSION") == "2025-01-01-preview"
    assert os.getenv("HERMES_MAX_OUTPUT_TOKENS") == "4096"
    assert os.getenv("HERMES_CONTEXT_WINDOW") == "128000"
    assert os.getenv("HERMES_REASONING_EFFORT") == "medium"
    assert os.getenv("TUSHARE_TOKEN") == "test-tushare-token"
    assert os.getenv("TIMEOUT_SECONDS") == "2400"
    assert os.getenv("MAX_RETRIES") == "5"


def test_get_hermes_agent_kwargs_caps_azure_max_tokens(monkeypatch):
    for key in (
        "HERMES_INFERENCE_PROVIDER",
        "HERMES_MAX_OUTPUT_TOKENS",
        "KIMI_MAX_OUTPUT_TOKENS",
        "HERMES_REASONING_EFFORT",
        "KIMI_REASONING_EFFORT",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("HERMES_INFERENCE_PROVIDER", "azure-openai")
    monkeypatch.setenv("HERMES_MAX_OUTPUT_TOKENS", "16384")
    monkeypatch.setattr(runtime_env, "_ENV_BOOTSTRAPPED", True)

    kwargs = runtime_env.get_hermes_agent_kwargs()

    assert kwargs["max_tokens"] == 4096


def test_get_hermes_agent_kwargs_preserves_primary_runtime(monkeypatch):
    for key in (
        "HERMES_INFERENCE_PROVIDER",
        "HERMES_MAX_OUTPUT_TOKENS",
        "KIMI_MAX_OUTPUT_TOKENS",
        "HERMES_REASONING_EFFORT",
        "KIMI_REASONING_EFFORT",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("HERMES_INFERENCE_PROVIDER", "alibaba")
    monkeypatch.setenv("HERMES_MAX_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("HERMES_REASONING_EFFORT", "medium")
    monkeypatch.setattr(runtime_env, "_ENV_BOOTSTRAPPED", True)

    fake_pkg = types.ModuleType("hermes_cli")
    fake_runtime_provider = types.ModuleType("hermes_cli.runtime_provider")

    def _fake_resolve_runtime_provider(*, requested=None, explicit_api_key=None, explicit_base_url=None):
        assert requested == "alibaba"
        assert explicit_api_key is None
        assert explicit_base_url is None
        return {
            "provider": "alibaba",
            "api_mode": "codex_responses",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "dashscope-test-key",
        }

    fake_runtime_provider.resolve_runtime_provider = _fake_resolve_runtime_provider

    monkeypatch.setitem(sys.modules, "hermes_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.runtime_provider", fake_runtime_provider)

    kwargs = runtime_env.get_hermes_agent_kwargs()

    assert kwargs["provider"] == "alibaba"
    assert kwargs["api_mode"] == "codex_responses"
    assert kwargs["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert kwargs["api_key"] == "dashscope-test-key"
    assert kwargs["max_tokens"] == 8192
    assert kwargs["reasoning_config"] == {"enabled": True, "effort": "medium"}


def test_get_hermes_agent_kwargs_reads_save_trajectories_env(monkeypatch):
    for key in ("SAVE_TRAJECTORIES", "HERMES_SAVE_TRAJECTORIES"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SAVE_TRAJECTORIES", "true")
    monkeypatch.setattr(runtime_env, "_ENV_BOOTSTRAPPED", True)

    kwargs = runtime_env.get_hermes_agent_kwargs()

    assert kwargs["save_trajectories"] is True


def test_get_hermes_agent_kwargs_reads_false_save_trajectories_env(monkeypatch):
    for key in ("SAVE_TRAJECTORIES", "HERMES_SAVE_TRAJECTORIES"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("HERMES_SAVE_TRAJECTORIES", "0")
    monkeypatch.setattr(runtime_env, "_ENV_BOOTSTRAPPED", True)

    kwargs = runtime_env.get_hermes_agent_kwargs()

    assert kwargs["save_trajectories"] is False


def test_ensure_runtime_env_clears_openai_base_url_for_named_provider(monkeypatch, tmp_path):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir(parents=True)
    (hermes_home / "config.yaml").write_text(
        """
model:
  provider: alibaba
  default: qwen3.5-plus
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  api_key: dashscope-test-key
""".strip()
        + "\n",
        encoding="utf-8",
    )

    for key in (
        "HERMES_HOME",
        "HERMES_INFERENCE_PROVIDER",
        "HERMES_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "LANGCHAIN_PROVIDER",
        "LANGCHAIN_MODEL_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.example/v1")
    monkeypatch.setattr(runtime_env, "_ENV_BOOTSTRAPPED", False)

    runtime_env.ensure_runtime_env()

    assert os.getenv("HERMES_INFERENCE_PROVIDER") == "alibaba"
    assert os.getenv("HERMES_MODEL") == "qwen3.5-plus"
    assert os.getenv("OPENAI_BASE_URL") is None


def test_ensure_runtime_env_ignores_configured_terminal_cwd(monkeypatch):
    monkeypatch.setenv("TERMINAL_CWD", "chris")
    monkeypatch.setattr(runtime_env, "_ENV_BOOTSTRAPPED", False)

    runtime_env.ensure_runtime_env()

    expected = str((runtime_env.AGENT_DIR.parent / "workspaces" / "public").resolve())
    assert os.getenv("TERMINAL_CWD") == expected
    assert runtime_env.get_data_root() == runtime_env.AGENT_DIR.parent / "workspaces" / "public"


def test_prepare_hermes_project_context_sets_repo_root(monkeypatch):
    monkeypatch.delenv("VIBE_TRADING_ROOT", raising=False)
    monkeypatch.delenv("HERMES_DISABLE_USER_PLUGINS", raising=False)
    monkeypatch.delenv("HERMES_DISABLE_PROJECT_PLUGINS", raising=False)

    repo_root = runtime_env.prepare_hermes_project_context(chdir=False)

    assert os.getenv("VIBE_TRADING_ROOT") == str(repo_root)
    assert os.getenv("HERMES_ENABLE_PROJECT_PLUGINS") in (None, "")
    assert os.getenv("HERMES_DISABLE_USER_PLUGINS") == "1"
    assert os.getenv("HERMES_DISABLE_PROJECT_PLUGINS") == "1"


def test_prepare_hermes_project_context_registers_local_plugin_without_entry_point(monkeypatch):
    import importlib.metadata as metadata
    import sys

    hermes_root = runtime_env.AGENT_DIR.parent / "hermes-agent"
    for path in (runtime_env.AGENT_DIR, hermes_root):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)

    monkeypatch.setattr(runtime_env, "_LOCAL_PLUGIN_BOOTSTRAPPED", False)

    def _empty_entry_points():
        return metadata.entry_points().__class__(()) if hasattr(metadata.entry_points(), "select") else []

    monkeypatch.setattr(runtime_env.importlib.metadata, "entry_points", _empty_entry_points)

    from tools.registry import registry

    repo_root = runtime_env.prepare_hermes_project_context(chdir=False)

    assert repo_root == runtime_env.AGENT_DIR.parent
    assert registry.get_entry("setup_backtest_run") is not None


def test_get_session_service_accepts_truthy_enable_session_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_SESSION_RUNTIME", " true ")
    monkeypatch.setattr(api_server, "_session_service", None, raising=False)
    monkeypatch.setattr(api_server, "_session_service_by_workspace", {}, raising=False)
    monkeypatch.setattr(api_server, "SESSIONS_DIR", tmp_path / "sessions", raising=False)
    monkeypatch.setattr(api_server, "RUNS_DIR", tmp_path / "runs", raising=False)

    service = api_server._get_session_service()

    assert service is not None


def test_get_env_bool_accepts_numeric_truthy(monkeypatch):
    monkeypatch.setenv("ENABLE_SESSION_RUNTIME", "1")

    assert api_server._get_env_bool("ENABLE_SESSION_RUNTIME") is True


def test_resolve_session_store_backend_defaults_to_file(monkeypatch):
    monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)

    assert api_server._resolve_session_store_backend() == "file"


def test_resolve_session_store_backend_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")

    assert api_server._resolve_session_store_backend() == "file"


def test_get_session_service_accepts_sqlite_backend_switch_for_future_migration(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_SESSION_RUNTIME", "true")
    monkeypatch.setenv("SESSION_STORE_BACKEND", "sqlite")
    monkeypatch.setattr(api_server, "_session_service", None, raising=False)
    monkeypatch.setattr(api_server, "_session_service_by_workspace", {}, raising=False)
    monkeypatch.setattr(api_server, "SESSIONS_DIR", tmp_path / "sessions", raising=False)
    monkeypatch.setattr(api_server, "RUNS_DIR", tmp_path / "runs", raising=False)

    service = api_server._get_session_service()

    assert service is not None
    assert service.store is not None
    assert service.store.__class__.__name__ == "SQLiteSessionStore"
    assert str(service.store.db_path).endswith(".hermes/state.db")


def test_resolve_frontend_paths_prefers_container_assets_over_host_checkout(tmp_path, monkeypatch):
    container_frontend = tmp_path / "app" / "frontend"
    host_repo = tmp_path / "home" / "chris" / "repo" / "Vibe-Trading"
    host_frontend = host_repo / "frontend"

    (container_frontend / "dist").mkdir(parents=True)
    host_frontend.mkdir(parents=True)

    monkeypatch.setattr(api_server, "_CONTAINER_FRONTEND_ROOT", container_frontend)
    monkeypatch.delenv("VIBE_TRADING_FRONTEND_ROOT", raising=False)
    monkeypatch.delenv("VIBE_TRADING_FRONTEND_DIST", raising=False)

    frontend_root, frontend_dist = api_server._resolve_frontend_paths(host_repo / "agent" / "api_server.py")

    assert frontend_root == container_frontend
    assert frontend_dist == container_frontend / "dist"


def test_resolve_frontend_paths_falls_back_to_repo_layout_without_container_assets(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_frontend = repo_root / "frontend"
    (repo_frontend / "dist").mkdir(parents=True)

    monkeypatch.setattr(api_server, "_CONTAINER_FRONTEND_ROOT", tmp_path / "missing-container-frontend")
    monkeypatch.delenv("VIBE_TRADING_FRONTEND_ROOT", raising=False)
    monkeypatch.delenv("VIBE_TRADING_FRONTEND_DIST", raising=False)

    frontend_root, frontend_dist = api_server._resolve_frontend_paths(repo_root / "agent" / "api_server.py")

    assert frontend_root == repo_frontend
    assert frontend_dist == repo_frontend / "dist"
