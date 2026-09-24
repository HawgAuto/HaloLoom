"""Build-input successor refreshes Codex source and runtime atomically."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts/build_release_inputs.py"
SPEC = importlib.util.spec_from_file_location("build_release_inputs", MODULE_PATH)
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_base(tmp_path):
    root = tmp_path / "base"
    runtime = root / "native-agent-runtime/codex-amd"
    source = root / "native-agent-source"
    (runtime / "bin").mkdir(parents=True)
    source.mkdir()
    (runtime / "bin/codex").write_bytes(b"historical executable bytes 0.153.4")
    (runtime / "LICENSE").write_text("license\n")
    (source / "codex-amd-source-rust-v0.153.4.tar.gz").write_bytes(b"old source")
    manifest = {
        "files": {
            "native-agent-runtime/codex-amd/bin/codex": sha(runtime / "bin/codex"),
            "native-agent-source/codex-amd-source-rust-v0.153.4.tar.gz":
                sha(source / "codex-amd-source-rust-v0.153.4.tar.gz"),
        }, "native_build": False, "promotion_authority": False,
        "native_agent_runtime": {
            "path": "native-agent-runtime/codex-amd", "version": "0.153.4",
            "entrypoint": "bin/codex", "executable_files": ["bin/codex"],
            "source_commit": "1" * 40,
            "files": {"bin/codex": sha(runtime / "bin/codex"), "LICENSE": sha(runtime / "LICENSE")},
        },
        "native_agent_source": {
            "path": "native-agent-source/codex-amd-source-rust-v0.153.4.tar.gz",
            "sha256": sha(source / "codex-amd-source-rust-v0.153.4.tar.gz"),
            "commit": "1" * 40, "scope": "complete source",
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    archive = tmp_path / "base.tar.gz"
    with tarfile.open(archive, "w:gz") as out:
        for path in sorted(root.rglob("*")):
            out.add(path, path.relative_to(root).as_posix(), recursive=False)
    return archive


def make_inputs(tmp_path):
    bundle = tmp_path / "bundle"
    (bundle / "bin").mkdir(parents=True)
    (bundle / "bin/codex-code-mode-host").write_text("sidecar")
    (bundle / "codex-path").mkdir()
    (bundle / "codex-path/rg").write_text("rg")
    binary = tmp_path / "codex-amd-patched"
    binary.write_text("#!/bin/sh\nprintf 'codex-cli 0.156.1\\n'\n")
    binary.chmod(0o755)
    source = tmp_path / "codex-amd-source-rust-v0.156.1-ad99406.tar.gz"
    source.write_bytes(b"new source 0.156.1")
    return bundle, binary, source


def test_successor_replaces_old_runtime_source_and_manifest(tmp_path):
    base = make_base(tmp_path)
    bundle, binary, source = make_inputs(tmp_path)
    output = tmp_path / "haloloom-v0.1.4-build-inputs.tar.gz"
    result = build.package_native_successor(
        base, output, bundle=bundle, binary=binary, source_archive=source,
        version="0.156.1", source_commit="ad994060e04547932f4a88fe21115916e4262f81",
    )
    assert result["archive_sha256"] == sha(output)
    with tarfile.open(output, "r:gz") as archive:
        names = set(archive.getnames())
        assert "native-agent-source/codex-amd-source-rust-v0.153.4.tar.gz" not in names
        assert "native-agent-source/codex-amd-source-rust-v0.156.1-ad99406.tar.gz" in names
        assert sum(name == "native-agent-runtime/codex-amd/bin/codex" for name in names) == 1
        assert archive.extractfile("native-agent-runtime/codex-amd/bin/codex").read() == binary.read_bytes()
        manifest = json.load(archive.extractfile("manifest.json"))
    assert manifest["native_agent_runtime"]["version"] == "0.156.1"
    assert manifest["native_agent_runtime"]["source_commit"] == "ad994060e04547932f4a88fe21115916e4262f81"
    assert manifest["native_agent_runtime"]["files"]["bin/codex"] == sha(binary)
    assert manifest["native_agent_source"]["sha256"] == sha(source)
    assert "0.153.4" not in json.dumps(manifest)


def test_successor_fails_if_binary_version_does_not_match(tmp_path):
    base = make_base(tmp_path)
    bundle, binary, source = make_inputs(tmp_path)
    with pytest.raises(build.InputError, match="version"):
        build.package_native_successor(
            base, tmp_path / "out.tar.gz", bundle=bundle, binary=binary,
            source_archive=source, version="0.156.0",
            source_commit="ad994060e04547932f4a88fe21115916e4262f81",
        )


def test_successor_fails_if_bundle_contains_duplicate_codex(tmp_path):
    base = make_base(tmp_path)
    bundle, binary, source = make_inputs(tmp_path)
    (bundle / "bin/codex").write_text("duplicate")
    with pytest.raises(build.InputError, match="must not contain.*codex"):
        build.package_native_successor(
            base, tmp_path / "out.tar.gz", bundle=bundle, binary=binary,
            source_archive=source, version="0.156.1",
            source_commit="ad994060e04547932f4a88fe21115916e4262f81",
        )
