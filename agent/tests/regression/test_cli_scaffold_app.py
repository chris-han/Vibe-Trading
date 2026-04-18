from __future__ import annotations

from pathlib import Path

import cli


def test_scaffold_app_creates_expected_custom_application_skeleton(tmp_path):
    result = cli.cmd_scaffold_app("Acme Research", str(tmp_path))

    assert result == cli.EXIT_SUCCESS

    project_root = tmp_path / "acme-research"
    expected_files = [
        project_root / "README.md",
        project_root / "pyproject.toml",
        project_root / "src" / "app_runtime.py",
        project_root / "src" / "adapters" / "factory.py",
        project_root / "src" / "adapters" / "feishu_visualization_adapter.py",
        project_root / "src" / "plugins" / "acme_research" / "__init__.py",
        project_root / "src" / "plugins" / "acme_research" / "schemas.py",
        project_root / "src" / "plugins" / "acme_research" / "tools.py",
        project_root / "src" / "skills" / "output-format-web" / "SKILL.md",
        project_root / "src" / "skills" / "output-format-feishu" / "SKILL.md",
        project_root / "tests" / "test_visualization_contracts.py",
        project_root / "tests" / "test_plugin_boundary.py",
    ]

    for file_path in expected_files:
        assert file_path.exists(), f"missing scaffolded file: {file_path}"

    plugin_init = (project_root / "src" / "plugins" / "acme_research" / "__init__.py").read_text(encoding="utf-8")
    assert "ctx.register_tool" in plugin_init

    adapter_factory = (project_root / "src" / "adapters" / "factory.py").read_text(encoding="utf-8")
    assert "FeishuVisualizationAdapter" in adapter_factory
    assert "WebVisualizationAdapter" in adapter_factory

    readme = (project_root / "README.md").read_text(encoding="utf-8")
    assert "Custom Hermes-based application scaffold" in readme
    assert "Hermes plugin registration surface" in readme
    assert "one component of the application scaffold" in readme
    assert "regression tests that lock in scaffold architecture rules" in readme

    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.optional-dependencies]" in pyproject
    assert 'pytest>=8.0' in pyproject

    visualization_tests = (project_root / "tests" / "test_visualization_contracts.py").read_text(encoding="utf-8")
    assert "test_channel_skill_set_matches_adapter_set" in visualization_tests
    assert "get_visualization_adapter" in visualization_tests

    plugin_boundary_tests = (project_root / "tests" / "test_plugin_boundary.py").read_text(encoding="utf-8")
    assert "test_plugin_registers_tools_through_hermes_surface" in plugin_boundary_tests
    assert "test_tool_handlers_do_not_embed_channel_payload_details" in plugin_boundary_tests


def test_scaffold_app_reports_custom_application_in_output(tmp_path, capsys):
    result = cli.cmd_scaffold_app("Acme Research", str(tmp_path))

    assert result == cli.EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "Scaffolded Custom Application" in output
    assert "Created custom application scaffold" in output


def test_scaffold_app_rejects_existing_non_empty_target(tmp_path):
    project_root = tmp_path / "acme-research"
    project_root.mkdir()
    (project_root / "placeholder.txt").write_text("occupied", encoding="utf-8")

    result = cli.cmd_scaffold_app("Acme Research", str(tmp_path))

    assert result == cli.EXIT_USAGE_ERROR


def test_main_dispatches_scaffold_app_command(tmp_path):
    result = cli.main(["scaffold-app", "Signal Forge", "--dest", str(tmp_path)])

    assert result == cli.EXIT_SUCCESS
    assert (tmp_path / "signal-forge" / "src" / "plugins" / "signal_forge" / "tools.py").exists()