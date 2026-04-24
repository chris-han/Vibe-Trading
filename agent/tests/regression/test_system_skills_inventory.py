from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import api_server
from hermes_cli import tools_config as hermes_tools_config
from hermes_cli import web_server as hermes_web_server
import toolsets


def _write_skill(skill_dir: Path, name: str, description: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "tags:\n"
            "  - finance\n"
            "---\n\n"
            f"# {name}\n"
        ),
        encoding="utf-8",
    )


def test_system_skills_reports_three_tiers_with_workspace_mutability(
    tmp_path: Path,
    monkeypatch,
):
    repo_root = tmp_path / "repo"
    workspaces_dir = repo_root / "workspaces"
    template_hermes_home = tmp_path / "template-hermes"

    monkeypatch.setattr(api_server, "REPO_ROOT", repo_root)
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "_TEMPLATE_HERMES_HOME", template_hermes_home)
    monkeypatch.setenv("VIBE_TRADING_ROOT", str(repo_root))

    _write_skill(
        repo_root / "agent" / "src" / "skills" / "app-infra" / "shared-alpha",
        "shared-alpha",
        "Application-wide shared skill",
    )
    _write_skill(
        repo_root / "hermes-agent" / "skills" / "core" / "builtin-beta",
        "builtin-beta",
        "Hermes built-in skill",
    )

    template_hermes_home.mkdir(parents=True, exist_ok=True)
    (template_hermes_home / "config.yaml").write_text(
        (
            "skills:\n"
            "  external_dirs:\n"
            "    - ${VIBE_TRADING_ROOT}/agent/src/skills\n"
            "    - ${VIBE_TRADING_ROOT}/hermes-agent/skills\n"
        ),
        encoding="utf-8",
    )

    public_workspace_home = workspaces_dir / "public" / ".hermes"
    _write_skill(
        public_workspace_home / "skills" / "workspace-gamma",
        "workspace-gamma",
        "Workspace-owned user skill",
    )

    client = TestClient(api_server.app)
    response = client.get("/system/skills")

    assert response.status_code == 200, response.text
    payload = response.json()
    skills = {entry["name"]: entry for entry in payload["skills"]}

    assert {"shared-alpha", "builtin-beta", "workspace-gamma"}.issubset(skills)

    assert skills["workspace-gamma"]["sourceTier"] == "workspace"
    assert skills["workspace-gamma"]["canUninstall"] is True
    assert skills["workspace-gamma"]["canEdit"] is True

    assert skills["shared-alpha"]["sourceTier"] == "application"
    assert skills["shared-alpha"]["canUninstall"] is True  # Admin (unauthenticated) can uninstall Semantier skills
    assert skills["shared-alpha"]["canEdit"] is False

    assert skills["builtin-beta"]["sourceTier"] == "builtin"
    assert skills["builtin-beta"]["canUninstall"] is False
    assert skills["builtin-beta"]["builtin"] is True


def test_system_skills_exposes_declared_config_fields(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    workspaces_dir = repo_root / "workspaces"
    template_hermes_home = tmp_path / "template-hermes"

    monkeypatch.setattr(api_server, "REPO_ROOT", repo_root)
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "_TEMPLATE_HERMES_HOME", template_hermes_home)
    monkeypatch.setenv("VIBE_TRADING_ROOT", str(repo_root))

    skill_dir = repo_root / "agent" / "src" / "skills" / "app-infra" / "feishu-search"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: feishu-search\n"
            "description: Search contacts and schedule meetings\n"
            "metadata:\n"
            "  hermes:\n"
            "    config:\n"
            "      - key: feishu.bot.identity\n"
            "        label: Bot identity\n"
            "        required: true\n"
            "      - key: feishu.bot.contact_scope\n"
            "        description: Department scope id\n"
            "        default: 0\n"
            "---\n\n"
            "# Feishu Search\n"
        ),
        encoding="utf-8",
    )

    template_hermes_home.mkdir(parents=True, exist_ok=True)
    (template_hermes_home / "config.yaml").write_text(
        "skills:\n  external_dirs:\n    - ${VIBE_TRADING_ROOT}/agent/src/skills\n",
        encoding="utf-8",
    )

    client = TestClient(api_server.app)
    response = client.get("/system/skills")

    assert response.status_code == 200, response.text
    payload = response.json()
    skill = next((entry for entry in payload["skills"] if entry["name"] == "feishu-search"), None)
    assert skill is not None
    assert skill["configFields"] == [
        {
            "key": "feishu.bot.identity",
            "label": "Bot identity",
            "type": "string",
            "required": True,
        },
        {
            "key": "feishu.bot.contact_scope",
            "description": "Department scope id",
            "type": "string",
            "default": 0,
        },
    ]


def test_system_skill_install_targets_active_workspace(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    workspaces_dir = repo_root / "workspaces"
    template_hermes_home = tmp_path / "template-hermes"

    monkeypatch.setattr(api_server, "REPO_ROOT", repo_root)
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "_TEMPLATE_HERMES_HOME", template_hermes_home)
    monkeypatch.setattr(api_server, "_feishu_oauth_enabled", lambda: False)

    template_hermes_home.mkdir(parents=True, exist_ok=True)
    (template_hermes_home / "config.yaml").write_text("skills:\n  external_dirs: []\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_install_skill_into_workspace(workspace, *, identifier: str, category: str = "", force: bool = False, config=None):
        captured["workspace"] = workspace
        captured["identifier"] = identifier
        captured["category"] = category
        captured["force"] = force
        captured["config"] = config
        return {
            "name": identifier,
            "install_path": f"{identifier}/SKILL.md",
            "sourceTier": "workspace",
            "sourceLabel": "Workspace",
        }

    monkeypatch.setattr(api_server, "_install_skill_into_workspace", fake_install_skill_into_workspace)

    client = TestClient(api_server.app)
    response = client.post(
        "/system/skills/install",
        json={
            "identifier": "market-skill",
            "category": "finance",
            "force": True,
            "config": {"feishu.bot.identity": "bot"},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["sourceTier"] == "workspace"
    assert captured["identifier"] == "market-skill"
    assert captured["category"] == "finance"
    assert captured["force"] is True
    assert captured["config"] == {"feishu.bot.identity": "bot"}
    assert captured["workspace"].hermes_home == workspaces_dir / "public" / ".hermes"


def test_install_skill_persists_declared_workspace_config(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    workspaces_dir = repo_root / "workspaces"
    template_hermes_home = tmp_path / "template-hermes"

    monkeypatch.setattr(api_server, "REPO_ROOT", repo_root)
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "_TEMPLATE_HERMES_HOME", template_hermes_home)
    monkeypatch.setattr(api_server, "_feishu_oauth_enabled", lambda: False)

    template_hermes_home.mkdir(parents=True, exist_ok=True)
    (template_hermes_home / "config.yaml").write_text("skills:\n  external_dirs: []\n", encoding="utf-8")

    workspace = api_server.ensure_workspace(workspaces_dir, "public", template_hermes_home, workspace_slug="public")
    skill_dir = workspace.hermes_home / "skills" / "productivity" / "feishu-bot-calendar"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: feishu-bot-calendar\n"
            "description: Bot calendar workspace skill\n"
            "metadata:\n"
            "  hermes:\n"
            "    config:\n"
            "      - key: feishu.bot.identity\n"
            "        description: Organizer identity for Feishu meeting workflows\n"
            "      - key: feishu.bot.timezone\n"
            "        description: Default timezone for scheduled meetings\n"
            "---\n\n"
            "# Feishu Bot Calendar\n"
        ),
        encoding="utf-8",
    )

    def fake_install_skill_from_hub(identifier: str, *, category: str = "", force: bool = False, invalidate_cache: bool = True):
        return {
            "name": identifier,
            "install_path": "productivity/feishu-bot-calendar/SKILL.md",
        }

    monkeypatch.setattr("hermes_cli.web_server._install_skill_from_hub", fake_install_skill_from_hub)

    result = api_server._install_skill_into_workspace(
        workspace,
        identifier="feishu-bot-calendar",
        category="productivity",
        config={
            "feishu.bot.identity": "bot",
            "feishu.bot.timezone": "Asia/Shanghai",
        },
    )

    assert result["appliedConfig"] == {
        "feishu.bot.identity": "bot",
        "feishu.bot.timezone": "Asia/Shanghai",
    }

    config_text = (workspace.hermes_home / "config.yaml").read_text(encoding="utf-8")
    assert "identity: bot" in config_text
    assert "timezone: Asia/Shanghai" in config_text


def test_install_skill_rejects_undeclared_workspace_config(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    workspaces_dir = repo_root / "workspaces"
    template_hermes_home = tmp_path / "template-hermes"

    monkeypatch.setattr(api_server, "REPO_ROOT", repo_root)
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "_TEMPLATE_HERMES_HOME", template_hermes_home)
    monkeypatch.setattr(api_server, "_feishu_oauth_enabled", lambda: False)

    template_hermes_home.mkdir(parents=True, exist_ok=True)
    (template_hermes_home / "config.yaml").write_text("skills:\n  external_dirs: []\n", encoding="utf-8")

    workspace = api_server.ensure_workspace(workspaces_dir, "public", template_hermes_home, workspace_slug="public")
    skill_dir = workspace.hermes_home / "skills" / "productivity" / "feishu-bot-calendar"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        (
            "---\n"
            "name: feishu-bot-calendar\n"
            "description: Bot calendar workspace skill\n"
            "metadata:\n"
            "  hermes:\n"
            "    config:\n"
            "      - key: feishu.bot.identity\n"
            "        description: Organizer identity for Feishu meeting workflows\n"
            "---\n\n"
            "# Feishu Bot Calendar\n"
        ),
        encoding="utf-8",
    )

    def fake_install_skill_from_hub(identifier: str, *, category: str = "", force: bool = False, invalidate_cache: bool = True):
        return {
            "name": identifier,
            "install_path": "productivity/feishu-bot-calendar/SKILL.md",
        }

    monkeypatch.setattr("hermes_cli.web_server._install_skill_from_hub", fake_install_skill_from_hub)

    try:
        api_server._install_skill_into_workspace(
            workspace,
            identifier="feishu-bot-calendar",
            category="productivity",
            config={"feishu.bot.unknown": "value"},
        )
    except api_server.HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["unknownKeys"] == ["feishu.bot.unknown"]
    else:
        raise AssertionError("Expected install-time config validation to fail")


def test_build_workspace_tool_inventory_reports_semantier_source_tiers(monkeypatch):
    monkeypatch.setattr(
        hermes_tools_config,
        "_get_effective_configurable_toolsets",
        lambda: [
            ("vibe_trading", "Vibe Trading", "Shared Semantier tools"),
            ("shell", "Shell", "Built-in shell tools"),
        ],
    )
    monkeypatch.setattr(
        hermes_tools_config,
        "_get_platform_tools",
        lambda config, platform, include_default_mcp_servers=False: ["vibe_trading", "shell"],
    )
    monkeypatch.setattr(
        hermes_tools_config,
        "_toolset_has_keys",
        lambda name, config=None: name == "vibe_trading",
    )
    monkeypatch.setattr(hermes_web_server, "load_config", lambda: {})
    monkeypatch.setattr(
        toolsets,
        "resolve_toolset",
        lambda name: ["portfolio_lookup"] if name == "vibe_trading" else ["bash"],
    )

    inventory = api_server._build_workspace_tool_inventory()
    tools = {entry["name"]: entry for entry in inventory}

    assert tools["vibe_trading"]["sourceTier"] == "application"
    assert tools["vibe_trading"]["sourceLabel"] == "Application Shared"
    assert tools["vibe_trading"]["configured"] is True

    assert tools["shell"]["sourceTier"] == "builtin"
    assert tools["shell"]["builtin"] is True
    assert tools["shell"]["configured"] is False


def test_system_skill_toggle_targets_active_workspace(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    workspaces_dir = repo_root / "workspaces"
    template_hermes_home = tmp_path / "template-hermes"

    monkeypatch.setattr(api_server, "REPO_ROOT", repo_root)
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "_TEMPLATE_HERMES_HOME", template_hermes_home)
    monkeypatch.setattr(api_server, "_feishu_oauth_enabled", lambda: False)

    template_hermes_home.mkdir(parents=True, exist_ok=True)
    (template_hermes_home / "config.yaml").write_text("skills:\n  external_dirs: []\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_toggle_workspace_skill(workspace, *, name: str, enabled: bool):
        captured["workspace"] = workspace
        captured["name"] = name
        captured["enabled"] = enabled
        return {"ok": True, "name": name, "enabled": enabled}

    monkeypatch.setattr(api_server, "_toggle_workspace_skill", fake_toggle_workspace_skill)

    client = TestClient(api_server.app)
    response = client.put(
        "/system/skills/toggle",
        json={"name": "workspace-gamma", "enabled": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    assert captured["name"] == "workspace-gamma"
    assert captured["enabled"] is False
    assert captured["workspace"].hermes_home == workspaces_dir / "public" / ".hermes"


def test_system_skill_uninstall_targets_active_workspace(monkeypatch, tmp_path: Path):
    repo_root = tmp_path / "repo"
    workspaces_dir = repo_root / "workspaces"
    template_hermes_home = tmp_path / "template-hermes"

    monkeypatch.setattr(api_server, "REPO_ROOT", repo_root)
    monkeypatch.setattr(api_server, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(api_server, "_TEMPLATE_HERMES_HOME", template_hermes_home)
    monkeypatch.setattr(api_server, "_feishu_oauth_enabled", lambda: False)

    template_hermes_home.mkdir(parents=True, exist_ok=True)
    (template_hermes_home / "config.yaml").write_text("skills:\n  external_dirs: []\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_uninstall_workspace_skill(workspace, *, name: str):
        captured["workspace"] = workspace
        captured["name"] = name
        return {"ok": True, "name": name, "message": "removed"}

    monkeypatch.setattr(api_server, "_uninstall_workspace_skill", fake_uninstall_workspace_skill)

    client = TestClient(api_server.app)
    response = client.post(
        "/system/skills/uninstall",
        json={"name": "workspace-gamma"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert captured["name"] == "workspace-gamma"
    assert captured["workspace"].hermes_home == workspaces_dir / "public" / ".hermes"