"""Container automation identity defaults; real CPU Git, isolated config."""
from pathlib import Path
import os
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECIPES = ["docker/ecosystem/Dockerfile", "docker/source-current/Dockerfile"]
BEGIN = "# BEGIN container automation identity"
END = "# END container automation identity"


def identity_setup(recipe):
    text = (ROOT / recipe).read_text()
    assert text.count(BEGIN) == text.count(END) == 1
    block = text.split(BEGIN, 1)[1].split(END, 1)[0].strip()
    assert block.startswith("RUN ")
    return re.sub(r"\\\n\s*", " ", block[4:])


def git(repo, env, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], env=env, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


@pytest.mark.parametrize("recipe", RECIPES)
@pytest.mark.parametrize("identity_source", ["empty", "system", "global", "local", "env"])
def test_clean_checkout_commit_and_revert_preserve_explicit_identity(tmp_path, recipe, identity_source):
    command = identity_setup(recipe)
    home = tmp_path / "home"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "EMAIL"}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / "xdg"),
               GIT_CONFIG_SYSTEM=str(tmp_path / "system.config"),
               GIT_CONFIG_GLOBAL=str(tmp_path / "global.config"))
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, env, "init", "-q")
    target = repo / "kernel.txt"
    target.write_text("baseline\n")
    git(repo, env, "add", "kernel.txt")
    # Preparation's command-only identity must not conceal the runtime gap.
    git(repo, env, "-c", "user.name=Preparation", "-c", "user.email=prepare@localhost",
        "commit", "-qm", "baseline")
    expected = ("KernelForge", "kernel-forge@localhost")
    if identity_source != "empty":
        expected = ("Explicit Author", "explicit@example.invalid")
        if identity_source == "env":
            env.update(GIT_AUTHOR_NAME=expected[0], GIT_COMMITTER_NAME=expected[0],
                       GIT_AUTHOR_EMAIL=expected[1], GIT_COMMITTER_EMAIL=expected[1])
        else:
            git(repo, env, "config", "--" + identity_source, "user.name", expected[0])
            git(repo, env, "config", "--" + identity_source, "user.email", expected[1])
    global_file = Path(env["GIT_CONFIG_GLOBAL"])
    before_global = global_file.read_bytes() if global_file.exists() else None
    subprocess.run(["sh", "-c", command], env=env, check=True, capture_output=True)
    # The recipe must neither require HOME config nor overwrite it.
    assert (global_file.read_bytes() if global_file.exists() else None) == before_global
    system_file = Path(env["GIT_CONFIG_SYSTEM"])
    once = system_file.read_bytes()
    subprocess.run(["sh", "-c", command], env=env, check=True, capture_output=True)
    assert system_file.read_bytes() == once
    target.write_text("candidate\n")
    git(repo, env, "add", "-u")
    git(repo, env, "commit", "-qm", "native-style keep")
    assert git(repo, env, "log", "-1", "--format=%an|%ae|%cn|%ce") == "|".join(expected + expected)
    git(repo, env, "revert", "--no-edit", "HEAD")
    assert target.read_text() == "baseline\n"


@pytest.mark.parametrize("recipe", RECIPES)
def test_invalid_system_config_remains_a_failure(tmp_path, recipe):
    config = tmp_path / "system.config"
    config.write_text("[broken\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=str(tmp_path), GIT_CONFIG_SYSTEM=str(config),
               GIT_CONFIG_GLOBAL=str(tmp_path / "global.config"))
    result = subprocess.run(["sh", "-c", identity_setup(recipe)], env=env, capture_output=True)
    assert result.returncode != 0
    assert config.read_text() == "[broken\n"
