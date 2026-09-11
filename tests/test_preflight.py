from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "preflight.py"
spec = importlib.util.spec_from_file_location("haloloom_preflight", MODULE_PATH)
assert spec and spec.loader
preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = preflight
spec.loader.exec_module(preflight)


def _probe(**overrides):
    data = {
        "docker": True,
        "compose": True,
        "kfd": True,
        "dri": True,
        "arch": "gfx1151",
        "hsa_override": None,
        "disk_free_bytes": 50 * 1024**3,
        "kfd_pids": [],
        "video_gid": 44,
        "render_gid": 992,
        "member_gids": [44, 992],
        "lock_available": True,
        "uid": 1000,
        "gid": 1000,
        "home": "/home/user",
        "cwd": "/work/HaloLoom",
    }
    data.update(overrides)
    return data


def test_assess_accepts_idle_native_gfx1151() -> None:
    report = preflight.assess(_probe(), allow_busy=False)
    assert report["passed"] is True
    assert report["errors"] == []


def test_assess_rejects_architecture_spoofing_and_wrong_arch() -> None:
    spoofed = preflight.assess(_probe(hsa_override="11.5.1"), allow_busy=False)
    assert spoofed["passed"] is False
    assert any("HSA_OVERRIDE_GFX_VERSION" in error for error in spoofed["errors"])

    wrong = preflight.assess(_probe(arch="gfx942"), allow_busy=False)
    assert wrong["passed"] is False
    assert any("gfx1151" in error for error in wrong["errors"])


def test_assess_fails_closed_on_busy_kfd_unless_explicitly_allowed() -> None:
    busy = preflight.assess(_probe(kfd_pids=[123, 456]), allow_busy=False)
    assert busy["passed"] is False
    assert any("/dev/kfd" in error for error in busy["errors"])

    allowed = preflight.assess(_probe(kfd_pids=[123]), allow_busy=True)
    assert allowed["passed"] is True
    assert any("/dev/kfd" in warning for warning in allowed["warnings"])


def test_render_env_contains_no_secret_fields() -> None:
    text = preflight.render_env(_probe())
    assert f"HALOLOOM_VERSION={preflight.release_version()}" in text
    assert "HOST_UID=1000" in text
    assert "VIDEO_GID=44" in text
    assert "RENDER_GID=992" in text
    assert "HF_HOME=/home/user/.cache/huggingface" in text
    assert "TOKEN" not in text
    assert "KEY" not in text
    assert "PASSWORD" not in text
