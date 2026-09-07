"""Exercise installer directory setup; external CLI probes are stubbed only."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_installer(tmp_path, cache):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts/install.sh", scripts / "install.sh")
    (scripts / "haloloom").write_text("#!/bin/sh\nexit 0\n")
    tools = tmp_path / "bin"
    tools.mkdir()
    # No hardware discovery, authentication, registry access or Docker launches.
    for tool in ("python3", "docker"):
        path = tools / tool
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    values = {
        "HF_HOME": str(cache),
        "HALOLOOM_WORKSPACE": str(tmp_path / "workspace"),
        "HALOLOOM_VERSION": "fixture",
        "HALOLOOM_AGENT_PROFILE": "codex",
    }
    (tmp_path / ".env").write_text("".join(f"{k}={shlex.quote(v)}\n" for k, v in values.items()))
    env = dict(os.environ, PATH=f"{tools}:/usr/bin:/bin")
    return subprocess.run(["bash", str(scripts / "install.sh"), "--no-pull", "--agent", "codex"],
                          env=env, capture_output=True, text=True, timeout=15)


def test_installer_prepares_missing_hf_cache_as_current_user(tmp_path):
    cache = tmp_path / "new home" / "HF cache"
    result = run_installer(tmp_path, cache)
    assert result.returncode == 0, result.stderr
    for path in (cache, cache / "hub", cache / "datasets", cache / "xet"):
        assert path.is_dir(), f"Docker would auto-create missing cache as root: {path}"
        assert path.stat().st_uid == os.getuid()
        marker = path / "write-check"
        marker.write_text("ok")
        marker.unlink()


@pytest.mark.skipif(os.getuid() == 0, reason="root bypasses POSIX write permissions")
def test_installer_rejects_unwritable_cache_without_chmod(tmp_path):
    cache = tmp_path / "unwritable"
    cache.mkdir(mode=0o555)
    try:
        result = run_installer(tmp_path, cache)
        assert result.returncode != 0, "installer must not report success for an unwritable mount"
        assert "Hugging Face cache" in result.stderr
        assert cache.stat().st_mode & 0o777 == 0o555
    finally:
        cache.chmod(0o755)


def test_installer_preserves_existing_cache_contents(tmp_path):
    cache = tmp_path / "existing"
    (cache / "hub").mkdir(parents=True)
    marker = cache / "hub" / "existing-file"
    marker.write_bytes(b"preserve existing cache bytes\n")
    before = marker.stat()
    result = run_installer(tmp_path, cache)
    assert result.returncode == 0, result.stderr
    assert marker.read_bytes() == b"preserve existing cache bytes\n"
    assert marker.stat().st_ino == before.st_ino
