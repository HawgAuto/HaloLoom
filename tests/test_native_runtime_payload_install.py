"""Fail-closed installation of the source-pinned native CLI payload."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install_native_agent_runtime.py"

def load():
    assert SCRIPT.is_file(), "native runtime installer is not implemented"
    spec = importlib.util.spec_from_file_location("native_runtime_install", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.fixture
def payload(tmp_path):
    root = tmp_path / "payload"
    runtime = root / "native-agent-runtime/codex-amd"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin/codex").write_text("#!/bin/sh\nprintf 'codex-cli 0.153.4\n'\n")
    (runtime / "LICENSE").write_text("Unit-test license fixture\n")
    spec = {"path": "native-agent-runtime/codex-amd", "version": "0.153.4",
            "entrypoint": "bin/codex", "executable_files": ["bin/codex"],
            "source_commit": "1" * 40,
            "files": {str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in runtime.rglob("*") if p.is_file()}}
    return root, runtime, spec, tmp_path / "installed"


def test_installs_and_verifies_with_exact_file_set(payload):
    root, runtime, spec, dest = payload
    module = load()
    first = module.install_runtime(root, spec, dest)
    second = module.install_runtime(root, spec, dest, verify_only=True)
    assert first == second
    assert first["files_verified"] == 2
    assert (dest / "bin/codex").stat().st_mode & 0o111


def test_tampered_payload_never_installs(payload):
    root, runtime, spec, dest = payload
    (runtime / "bin/codex").write_text("modified")
    with pytest.raises((ValueError, AssertionError), match="digest|hash"):
        load().install_runtime(root, spec, dest)
    assert not dest.exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute"])
def test_unsafe_manifest_paths_rejected(payload, name):
    root, runtime, spec, dest = payload
    spec["files"][name] = "0" * 64
    with pytest.raises((ValueError, AssertionError), match="path"):
        load().install_runtime(root, spec, dest)
    assert not dest.exists()


def test_payload_symlink_rejected(payload):
    root, runtime, spec, dest = payload
    source = runtime / "bin/codex"
    source.unlink()
    source.symlink_to(runtime / "LICENSE")
    with pytest.raises((ValueError, AssertionError), match="symlink"):
        load().install_runtime(root, spec, dest)
    assert not dest.exists()


def test_undeclared_payload_file_rejected(payload):
    root, runtime, spec, dest = payload
    (runtime / "auth.json").write_text("unit-test secret sentinel")
    with pytest.raises((ValueError, AssertionError), match="file set|undeclared"):
        load().install_runtime(root, spec, dest)
    assert not dest.exists()


def test_verify_only_detects_modified_installed_binary(payload):
    root, runtime, spec, dest = payload
    module = load()
    module.install_runtime(root, spec, dest)
    (dest / "bin/codex").write_text("changed")
    with pytest.raises((ValueError, AssertionError), match="digest|hash"):
        module.install_runtime(root, spec, dest, verify_only=True)


def test_verify_only_does_not_create_missing_destination(payload):
    root, runtime, spec, dest = payload
    with pytest.raises((ValueError, AssertionError, FileNotFoundError)):
        load().install_runtime(root, spec, dest, verify_only=True)
    assert not dest.exists()
