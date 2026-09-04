from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "detect_agent_plugins.py"
spec = importlib.util.spec_from_file_location("haloloom_agent_plugins", MODULE_PATH)
assert spec and spec.loader
plugins = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugins
spec.loader.exec_module(plugins)


def _executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_detects_all_three_host_agent_install_shapes(tmp_path: Path) -> None:
    path_bin = tmp_path / "path-bin"
    path_bin.mkdir()

    claude_real = _executable(tmp_path / "claude-root" / "claude")
    (path_bin / "claude").symlink_to(claude_real)

    codex_real = _executable(
        tmp_path / "codex-prefix" / "lib" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js",
        "#!/usr/bin/env node\n",
    )
    (path_bin / "codex").symlink_to(codex_real)

    hermes_real = _executable(tmp_path / "hermes-project" / "venv" / "bin" / "hermes")
    (path_bin / "hermes").symlink_to(hermes_real)

    result = plugins.detect_plugins(
        path_env=str(path_bin), home=tmp_path / "home", state_dir=tmp_path / "state"
    )

    assert result["available"] == ["claude", "codex", "hermes"]
    assert result["selected"] == "codex"
    env = result["env"]
    assert env["HALOLOOM_CODEX_ROOT_HOST"] == str(codex_real.parents[1])
    assert env["HALOLOOM_CODEX_BIN_HOST"] == str(codex_real.resolve())
    assert env["HALOLOOM_CLAUDE_ROOT_HOST"].startswith(str(tmp_path / "state" / "empty"))
    assert env["HALOLOOM_HERMES_ROOT_HOST"].startswith(str(tmp_path / "state" / "empty"))
    assert env["CLAUDE_HOME_HOST"].startswith(str(tmp_path / "state" / "empty"))
    assert env["HERMES_HOME_HOST"].startswith(str(tmp_path / "state" / "empty"))


def test_explicit_agent_must_exist(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "codex")
    with pytest.raises(RuntimeError, match="requested agent 'hermes' is not available"):
        plugins.detect_plugins(
            path_env=str(bin_dir),
            home=tmp_path / "home",
            state_dir=tmp_path / "state",
            requested="hermes",
        )


def test_writes_only_plugin_paths_and_selection(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "claude")
    result = plugins.detect_plugins(
        path_env=str(bin_dir), home=tmp_path / "home", state_dir=tmp_path / "state"
    )
    env_file = tmp_path / ".env"
    env_file.write_text("HF_TOKEN=do-not-touch\nHALOLOOM_AGENT_PROFILE=old\n", encoding="utf-8")
    plugins.write_env(env_file, result["env"])
    text = env_file.read_text(encoding="utf-8")
    assert "HF_TOKEN=do-not-touch" in text
    assert "HALOLOOM_AGENT_PROFILE=claude" in text
    assert "API_KEY" not in "\n".join(
        line for line in text.splitlines() if line.startswith("HALOLOOM_")
    )
    assert os.stat(env_file).st_mode & 0o077 == 0
