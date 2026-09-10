"""The pinned image runtime is independent of the host CLI install."""
import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "docker/ecosystem/workbench-entrypoint"

@pytest.fixture(autouse=True, params=["docker/ecosystem/workbench-entrypoint",
                                    "docker/quark/plugin-entrypoint"])
def selected_entrypoint(request, monkeypatch):
    import sys
    monkeypatch.setattr(sys.modules[__name__], "ENTRYPOINT", ROOT / request.param)

@pytest.fixture
def environment(tmp_path):
    env = dict(os.environ)
    home = tmp_path / "home"
    home.mkdir()
    env.update(HOME=str(home), CODEX_HOME=str(tmp_path / "auth"),
               HALOLOOM_AGENT_PROFILE="codex", HALOLOOM_NATIVE_PREFLIGHT="0",
               GIT_CONFIG_GLOBAL=str(tmp_path / "gitconfig"),
               GIT_CONFIG_SYSTEM=str(tmp_path / "system-gitconfig"))
    env.pop("HALOLOOM_CODEX_BIN_IMAGE", None)
    image = tmp_path / "image-codex"
    host = tmp_path / "host-codex"
    for path, label in ((image, "image-runtime"), (host, "host-runtime")):
        path.write_text("#!/bin/sh\nprintf '%s\n' '" + label + "'\n")
        path.chmod(0o755)
    env["HALOLOOM_CODEX_BIN_HOST"] = str(host)
    return env, image, host


def run(env):
    return subprocess.run(["bash", str(ENTRYPOINT), "agent-check"], env=env,
                          cwd=ENTRYPOINT.parents[2], capture_output=True, text=True)


def test_explicit_image_runtime_wins_over_detected_host(environment):
    env, image, host = environment
    env["HALOLOOM_CODEX_BIN_IMAGE"] = str(image)
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert "image-runtime" in result.stdout
    assert "host-runtime" not in result.stdout


def test_broken_explicit_image_runtime_does_not_fall_back(environment):
    env, image, host = environment
    env["HALOLOOM_CODEX_BIN_IMAGE"] = str(image.with_name("missing-runtime"))
    result = run(env)
    assert result.returncode != 0
    assert "host-runtime" not in result.stdout


def test_explicit_empty_image_override_retains_host_opt_in(environment):
    env, image, host = environment
    env["HALOLOOM_CODEX_BIN_IMAGE"] = ""
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert "host-runtime" in result.stdout
