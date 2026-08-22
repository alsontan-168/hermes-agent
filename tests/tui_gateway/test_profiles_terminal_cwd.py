"""Gateway-side project-folder binding for bot profiles.

``profiles.configure`` accepts ``terminal_cwd`` (absolute or '~'-prefixed
path, stored as the profile's ``terminal.cwd``; None/empty clears it) and
``profiles.describe`` reports the resolved value as ``terminal_cwd``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import tui_gateway.server as srv


@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    profile = home / "profiles" / "testbot"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("{}\n")
    return home


def _configure(params):
    return srv._methods["profiles.configure"]("c", params)["result"]["applied"]


def _describe(name="testbot"):
    return srv._methods["profiles.describe"]("d", {"name": name})["result"]


def _raw_config(profile_env):
    path = profile_env / "profiles" / "testbot" / "config.yaml"
    return yaml.safe_load(path.read_text()) or {}


def test_set_terminal_cwd_writes_profile_config(profile_env):
    project = profile_env / "my-project"
    project.mkdir()

    applied = _configure({"name": "testbot", "terminal_cwd": str(project)})

    assert applied["terminal_cwd"] is True
    assert _raw_config(profile_env)["terminal"]["cwd"] == str(project.resolve())
    assert _describe()["terminal_cwd"] == str(project.resolve())


def test_tilde_path_expands_to_real_home(profile_env):
    applied = _configure({"name": "testbot", "terminal_cwd": "~"})

    assert applied["terminal_cwd"] is True
    expected = Path(os_expanduser("~"))
    assert _raw_config(profile_env)["terminal"]["cwd"] == str(expected)


def test_nonexistent_directory_is_rejected(profile_env):
    before = _raw_config(profile_env)

    applied = _configure(
        {"name": "testbot", "terminal_cwd": str(profile_env / "missing")}
    )

    assert applied["terminal_cwd"] is False
    assert _raw_config(profile_env) == before


def test_clear_removes_user_value_and_describe_reports_default_resolved(
    profile_env,
):
    project = profile_env / "my-project"
    project.mkdir()
    _configure({"name": "testbot", "terminal_cwd": str(project)})

    applied = _configure({"name": "testbot", "terminal_cwd": None})

    assert applied["terminal_cwd"] is True
    assert "cwd" not in _raw_config(profile_env).get("terminal", {})
    # Default terminal.cwd='.' resolves to the profile home itself.
    profile_dir = (profile_env / "profiles" / "testbot").resolve()
    assert _describe()["terminal_cwd"] == str(profile_dir)


def os_expanduser(p):
    import os

    return os.path.expanduser(p)
