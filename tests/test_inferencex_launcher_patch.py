"""Offline integrity checks; pinned upstream patch replay is separate evidence."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = ROOT / "patches/inferencex"


def manifest():
    return json.loads((PATCH_DIR / "manifest.json").read_text())


def test_inferencex_patch_is_hash_bound_to_declared_source():
    m = manifest()
    patch = PATCH_DIR / m["patch"]
    assert patch.parent == PATCH_DIR
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == m["patch_sha256"]
    for field in ("base_ref", "base_tree", "patched_tree"):
        assert re.fullmatch(r"[0-9a-f]{40}", m[field])
    for field in ("base_launcher_sha256", "accepted_pre_loopback_sha256", "accepted_launcher_sha256"):
        assert re.fullmatch(r"[0-9a-f]{64}", m[field])


def test_patch_touches_only_the_launcher_and_additive_tests():
    m = manifest()
    result = subprocess.run(
        ["git", "apply", "--numstat", str(PATCH_DIR / m["patch"])],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    files = [line.split("\t", 2)[2] for line in result.stdout.splitlines()]
    assert sorted(files) == sorted(m["changed_files"])
    assert set(files) == {
        "benchmarks/benchmark_lib.sh", "tests/test_haloloom_benchmark_launcher.py"
    }


def test_source_checkpoint_does_not_claim_an_installed_runtime():
    m = manifest()
    checkpoints = json.loads((ROOT / "manifests/source-fixes-20260926.json").read_text())
    row = checkpoints["portable_patches"]["InferenceX_launcher"]
    assert (ROOT / row["patch"]).read_bytes() == (PATCH_DIR / m["patch"]).read_bytes()
    assert row["patch_sha256"] == m["patch_sha256"]
    assert row["base_ref"] == m["base_ref"]
    assert row["delivery"] == m["delivery"] == "portable_patch_not_public_component_commit"
    assert row["automatically_applied_by_stable_installer"] is False
    assert m["automatically_applied_by_stable_installer"] is False
    assert m["local_preparation_commit_publicly_fetchable"] is False
    assert m["server_bind_arguments_changed"] is False
