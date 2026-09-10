"""Ensure the shipping entrypoint selects the real native hook sandbox."""
from pathlib import Path
import json
import os
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def configure(tmp_path, *, profile="codex", extra=None):
    source = (ROOT / "docker/ecosystem/workbench-entrypoint").read_text()
    marker = f"  {profile})\n"
    start = source.index(marker) + len(marker)
    branch = source[start:source.index("    ;;", start)]
    branch = branch.replace("native_home=/tmp/haloloom-codex-home",
                            "native_home=" + shlex.quote(str(tmp_path / "private")))
    home = tmp_path / "login"
    home.mkdir()
    (home / "auth.json").write_text("{}")
    env = {"PATH": os.defpath, "HOME": str(tmp_path), "CODEX_HOME": str(home),
           "HALOLOOM_CODEX_BIN_HOST": "/bin/true", "HALOLOOM_CLAUDE_BIN_HOST": "/bin/true"}
    env.update(extra or {})
    report = "python3 -c 'import os,json;print(json.dumps(os.environ.get(\"FORGE_AGENT_SANDBOX_MODE\")))'"
    result = subprocess.run(["bash", "-c", "set -euo pipefail\n" + branch + "\n" + report],
                            env=env, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_native_oauth_forge_defaults_to_contained_hooks(tmp_path):
    assert configure(tmp_path) == "workspace-write"


def test_codex_gateway_uses_the_same_hook_protection(tmp_path):
    assert configure(tmp_path, extra={"OPENAI_BASE_URL": "https://invalid.example"}) == "workspace-write"


@pytest.mark.parametrize("explicit", ["read-only", "workspace-write", "bypass"])
def test_explicit_choice_is_not_silently_rewritten(tmp_path, explicit):
    # The adapter rejects explicit bypass with hooks; the entrypoint must not
    # misreport operator intent by silently changing it.
    assert configure(tmp_path, extra={"FORGE_AGENT_SANDBOX_MODE": explicit}) == explicit


def test_claude_branch_is_unchanged(tmp_path):
    assert configure(tmp_path, profile="claude") is None
