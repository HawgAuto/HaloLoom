"""Regression for compaction of an image with a non-root working directory."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "compact_codex_image.py"
SPEC = importlib.util.spec_from_file_location("haloloom_compact_workdir", MODULE)
assert SPEC is not None and SPEC.loader is not None
compact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compact)


def source(workdir="/workspace"):
    return {"Id": "sha256:" + "a" * 64, "Config": {
        "Labels": {"haloloom.promotion_authority": "false"},
        "WorkingDir": workdir, "User": "1000:1000",
    }}


def test_workdir_is_restored_only_after_single_layer_copy():
    recipe = compact.dockerfile("quark:candidate", source(), True, {})
    assert "FROM scratch\nCOPY --from=resolved / /" in recipe
    assert "WORKDIR /workspace" not in recipe
    assert "USER 1000:1000" in recipe
    assert "/opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py" in recipe


def test_legacy_metadata_build_restores_workdir_without_losing_shell():
    captured = []
    def build(command, **kwargs):
        captured.append((command, kwargs, (Path(command[-1]) / "Dockerfile").read_text()))
    with patch.object(compact, "image", return_value={"Id": "sha256:" + "a" * 64}), \
         patch.object(compact.subprocess, "run", side_effect=build):
        compact.restore_workdir("stage:local", "target:local", "/workspace")
    command, kwargs, recipe = captured[0]
    assert command[:-1] == ["docker", "build", "--pull=false", "--network=none", "-t", "target:local"]
    assert kwargs["env"]["DOCKER_BUILDKIT"] == "0"
    assert recipe == "FROM sha256:" + "a" * 64 + "\nWORKDIR /workspace\n"


@pytest.mark.parametrize("workdir", ["relative", "/unsafe\nRUN false", "/bad\x00dir", "/with space"])
def test_unsafe_workdir_rejected(workdir):
    with pytest.raises(ValueError, match="Unsafe working directory"):
        compact.dockerfile("quark:candidate", source(workdir), False, {})
