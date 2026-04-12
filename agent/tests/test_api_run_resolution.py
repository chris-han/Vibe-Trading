from pathlib import Path

import api_server


def test_resolve_run_dir_falls_back_to_legacy_root(tmp_path: Path, monkeypatch):
    configured_runs = tmp_path / "chris" / "runs"
    configured_runs.mkdir(parents=True)

    legacy_runs = tmp_path / "runs"
    expected = legacy_runs / "20260412_081103_28_cf78e7"
    expected.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", configured_runs)
    monkeypatch.setattr(api_server, "LEGACY_RUNS_DIR", legacy_runs)

    resolved = api_server._resolve_run_dir(expected.name)

    assert resolved == expected


def test_collect_run_dirs_prefers_primary_root_on_duplicates(tmp_path: Path, monkeypatch):
    configured_runs = tmp_path / "chris" / "runs"
    legacy_runs = tmp_path / "runs"

    preferred = configured_runs / "shared_run"
    fallback = legacy_runs / "shared_run"
    unique_legacy = legacy_runs / "legacy_only"

    preferred.mkdir(parents=True)
    fallback.mkdir(parents=True)
    unique_legacy.mkdir(parents=True)

    monkeypatch.setattr(api_server, "RUNS_DIR", configured_runs)
    monkeypatch.setattr(api_server, "LEGACY_RUNS_DIR", legacy_runs)

    run_dirs = api_server._collect_run_dirs()
    by_name = {d.name: d for d in run_dirs}

    assert by_name["shared_run"] == preferred
    assert by_name["legacy_only"] == unique_legacy
