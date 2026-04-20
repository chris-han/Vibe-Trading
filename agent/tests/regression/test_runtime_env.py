from __future__ import annotations

import os
import sys
import types

import runtime_env



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
