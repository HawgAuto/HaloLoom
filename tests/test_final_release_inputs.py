"""The public release must bind real source-current inputs, not placeholders."""
import json
import os
from pathlib import Path
import runpy
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REF = "bb64a30177e8aa80a1a54d5c64f3b1a0d97078b5"
WHEEL_SHA256 = "4f49d5a7fd745c78fbf34e2f13d05379b45b5abfc7e0b1d4afefafc53a97c1eb"


def test_public_default_build_manifest_is_complete():
    build = runpy.run_path(str(ROOT / "scripts/build_release_inputs.py"))
    manifest = build["load_manifest"](ROOT / "manifests/build-inputs.json")
    assert set(manifest["images"]) == {"vllm", "sglang", "quark", "aiter-tools"}
    assert manifest["overlay_archive"]["url"] == (
        "https://github.com/HawgAuto/HaloLoom/releases/download/v0.1.2/"
        "haloloom-v0.1.2-build-inputs.tar.gz"
    )


def test_release_hyperloom_identity_is_the_qualified_source_current_wheel():
    component = json.loads((ROOT / "manifests/components.json").read_text())["components"]["hyperloom"]
    assert component["commit"] == SOURCE_REF
    assert component["wheel_sha256"] == WHEEL_SHA256


def test_release_checksum_closure_includes_the_public_rebuild_archive():
    manifest = json.loads((ROOT / "manifests/build-inputs.json").read_text())
    asset = manifest["overlay_archive"]
    sums = dict(line.split("  ", 1)[::-1] for line in (ROOT / "release/SHA256SUMS").read_text().splitlines())
    assert sums[asset["filename"]] == asset["sha256"]
    assert sums["hyperloom_inference_optimizer-1.0.0-py3-none-any.whl"] == WHEEL_SHA256


def test_source_build_context_excludes_operator_and_campaign_state():
    rules = (ROOT / "docker/source-current/Dockerfile.dockerignore").read_text().splitlines()
    assert rules == [
        "**", "!docker/", "!docker/source-current/",
        "!docker/source-current/Dockerfile", "!docker/source-current/Dockerfile.dockerignore",
        "!dist/", "!dist/source-current/", "!dist/source-current/**",
        "dist/source-current/*.tar.gz",
    ]


def test_downloaded_archive_preserves_usable_bare_git_transport(tmp_path):
    archive = Path(os.environ.get(
        "HALOLOOM_BUILD_INPUTS_UNDER_TEST",
        str(ROOT / "dist/haloloom-v0.1.2-build-inputs.tar.gz"),
    ))
    if not archive.is_file():
        pytest.skip("release-asset gate; source-only clones need not contain dist")
    build = runpy.run_path(str(ROOT / "scripts/build_release_inputs.py"))
    stage = tmp_path / "unpacked"
    build["extract_archive"](archive, stage)
    result = subprocess.run(
        ["git", "ls-remote", str(stage / "sglang-snapshot.git"), "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split()[0] == "90c62e027831111934a33b9bcc4e533ff61d8526"
