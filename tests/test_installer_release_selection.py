"""Release-selection regressions; no device, provider or registry calls."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_preflight(root):
    spec = importlib.util.spec_from_file_location(
        "release_selection_preflight", root / "scripts/preflight.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe():
    return {
        "docker": True, "compose": True, "kfd": True, "dri": True,
        "arch": "gfx1151", "hsa_override": None, "disk_free_bytes": 50 * 1024**3,
        "video_gid": 44, "render_gid": 992, "member_gids": [44, 992],
        "lock_available": True, "kfd_pids": [], "uid": 1000, "gid": 1000,
        "home": "/home/user", "cwd": "/work/HaloLoom",
    }


def fixture_checkout(tmp_path, manifest):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "manifests").mkdir()
    shutil.copyfile(ROOT / "scripts/preflight.py", tmp_path / "scripts/preflight.py")
    (tmp_path / "manifests/components.json").write_text(manifest)
    return load_preflight(tmp_path)


def test_generated_version_matches_published_component_images():
    manifest = json.loads((ROOT / "manifests/components.json").read_text())
    text = load_preflight(ROOT).render_env(probe())
    version = dict(line.split("=", 1) for line in text.splitlines())["HALOLOOM_VERSION"]
    assert version == manifest["release"]
    for key in ("full_vllm", "full_sglang", "quark", "aiter_tools"):
        assert manifest["images"][key]["reference"].endswith(":" + version)


@pytest.mark.parametrize("version", ["v0.1.2", "v1.2.3", "v2.0.0-rc1"])
def test_release_bump_requires_no_preflight_source_edit(tmp_path, version):
    module = fixture_checkout(tmp_path, json.dumps({"release": version}))
    assert f"HALOLOOM_VERSION={version}\n" in module.render_env(probe())


def test_uses_own_checkout_not_cwd_or_inherited_version(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    module = fixture_checkout(checkout, '{"release": "v1.2.3"}')
    other = tmp_path / "other"
    (other / "manifests").mkdir(parents=True)
    (other / "manifests/components.json").write_text('{"release": "v0.1.1"}')
    monkeypatch.chdir(other)
    monkeypatch.setenv("HALOLOOM_VERSION", "v0.1.1")
    assert "HALOLOOM_VERSION=v1.2.3\n" in module.render_env(probe())


@pytest.mark.parametrize("manifest", [
    "{}", "[]", "null", "not json", '{"release": null}',
    '{"release": 2}', '{"release": "latest"}', '{"release": "v01.2.3"}',
    '{"release": "v0.1.2\\nTOKEN=bad"}', '{"release": "v0.1.2;false"}',
])
def test_invalid_manifest_cannot_fall_back_to_an_old_release(tmp_path, manifest):
    module = fixture_checkout(tmp_path, manifest)
    with pytest.raises(ValueError):
        module.render_env(probe())


def test_missing_manifest_cannot_fall_back(tmp_path):
    module = fixture_checkout(tmp_path, '{"release": "v1.2.3"}')
    (tmp_path / "manifests/components.json").unlink()
    with pytest.raises(OSError):
        module.render_env(probe())


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_manifest_failure_preserves_existing_env(tmp_path, monkeypatch, capsys, json_output):
    module = fixture_checkout(tmp_path, "{}")
    env_file = tmp_path / ".env"
    original = b"HALOLOOM_VERSION=v0.1.1\nPRESERVE=existing\n"
    env_file.write_bytes(original)
    # Hardware discovery is the only stub; render/validate/write/report are real.
    monkeypatch.setattr(module, "live_probe", probe)
    args = ["preflight.py", "--write-env", str(env_file)]
    if json_output:
        args.append("--json")
    monkeypatch.setattr(sys, "argv", args)
    assert module.main() == 1
    assert env_file.read_bytes() == original
    output = capsys.readouterr().out
    if json_output:
        report = json.loads(output)
        assert report["passed"] is False
        assert any("release" in error.lower() for error in report["errors"])
    else:
        assert "HALOLOOM_PREFLIGHT_FAILED" in output
