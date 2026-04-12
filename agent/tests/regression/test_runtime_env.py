from __future__ import annotations

import os

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


def test_prepare_hermes_project_context_sets_repo_root(monkeypatch):
  monkeypatch.delenv("VIBE_TRADING_ROOT", raising=False)

  repo_root = runtime_env.prepare_hermes_project_context(chdir=False)

  assert os.getenv("VIBE_TRADING_ROOT") == str(repo_root)
  assert os.getenv("HERMES_ENABLE_PROJECT_PLUGINS") in (None, "")
