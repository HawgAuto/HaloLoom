"""CPU-only regressions for source identity and opt-in loader closures."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def api():
    spec = importlib.util.spec_from_file_location(
        "reconciled_full_release", ROOT / "docker/full-release/apply_and_verify.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True
    ).strip()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    git(root, "init", "-q")
    (root / "runtime.py").write_text("VALUE = 'accepted'\n")
    git(root, "add", "runtime.py")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "fixture source")
    spec = {
        "ref": git(root, "rev-parse", "HEAD"),
        "tree": git(root, "rev-parse", "HEAD^{tree}"),
        "files": {"runtime.py": hashlib.sha256((root / "runtime.py").read_bytes()).hexdigest()},
    }
    return root, spec


def test_verified_committed_source_is_present_in_specialist_worktree(source, tmp_path):
    root, spec = source
    api().verify_tree(root, spec)
    worktree = tmp_path / "specialist"
    git(root, "worktree", "add", "--detach", str(worktree), spec["ref"])
    api().verify_tree(worktree, spec)
    assert (worktree / "runtime.py").read_bytes() == (root / "runtime.py").read_bytes()


def test_dirty_source_cannot_masquerade_as_committed_runtime(source):
    root, spec = source
    (root / "runtime.py").write_text("VALUE = 'uncommitted-shadow'\n")
    with pytest.raises(AssertionError):
        api().verify_tree(root, spec)


@pytest.mark.parametrize("field", ["ref", "tree"])
def test_wrong_source_identity_is_rejected(source, field):
    root, spec = source
    spec[field] = "0" * 40
    with pytest.raises(AssertionError):
        api().verify_tree(root, spec)


def test_wrong_installed_source_hash_is_rejected(source):
    root, spec = source
    spec["files"]["runtime.py"] = "0" * 64
    with pytest.raises(AssertionError):
        api().verify_tree(root, spec)


def test_full_runtime_loader_paths_are_explicit_opt_in():
    assert not (ROOT / "compose.override.yaml").exists()
    overlay = yaml.safe_load((ROOT / "docker/full-release/compose.runtime.yaml").read_text())
    assert set(overlay) == {"services"}
    assert set(overlay["services"]) == {"vllm", "quark", "sglang"}
    for service in overlay["services"].values():
        assert set(service) == {"environment"}
        assert set(service["environment"]) == {"LD_LIBRARY_PATH"}
    paths = {name: row["environment"]["LD_LIBRARY_PATH"]
             for name, row in overlay["services"].items()}
    assert paths["vllm"] == paths["quark"]
    assert paths["sglang"] != paths["vllm"]
    assert paths["vllm"].index("_rocm_sdk_core/lib:") < paths["vllm"].index("/opt/rocm/core-10.0/lib:")
    assert paths["sglang"].startswith("/opt/venv/lib/python3.14/site-packages/torch/lib:")
