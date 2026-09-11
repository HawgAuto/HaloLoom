"""CPU-only regressions for the supported local candidate input path."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest
from test_public_build_inputs import build_inputs, manifest, make_tar, write_manifest


def packet(tmp_path, *, sources_raw=None, extra=()):
    sources = {name: {"ref": str(i) * 40, "tree": str(i + 3) * 40}
               for i, name in enumerate(("GEAK", "Hyperloom", "HaloLoom"), 1)}
    archive = tmp_path / "candidate.tgz"
    make_tar(archive, [(tarfile.TarInfo("candidate-sources.json"),
                        (sources_raw or json.dumps(sources)).encode()),
                       (tarfile.TarInfo("apply-and-verify.py"), b"# parent supplies real installer\n"),
                       *extra])
    data = manifest(archive)
    data.update(schema_version=2, version="candidate-Qwen.27B-001", sources=sources)
    data["overlay_archive"] = {"filename": archive.name,
                               "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    for name, row in data["images"].items():
        row["local_tag"] = f"haloloom-{name}:candidate-unique-001"
    return archive, data


@pytest.fixture(autouse=True)
def forbid_real_operations(monkeypatch):
    monkeypatch.setattr(build_inputs, "download_https", lambda *a, **k: pytest.fail("candidate must not download"))
    monkeypatch.setattr(build_inputs.urllib.request, "urlopen", lambda *a, **k: pytest.fail("no network"))
    monkeypatch.setattr(build_inputs.subprocess, "run", lambda *a, **k: pytest.fail("unexpected Docker action"))


def docker_stub(monkeypatch, *, failure=None):
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            assert kwargs["capture_output"] and kwargs["text"]
            if failure and command[-1].startswith("haloloom-aiter-tools:"):
                return subprocess.CompletedProcess(command, *failure)
            return subprocess.CompletedProcess(command, 1, "", f"Error response from daemon: No such image: {command[-1]}\n")
        assert kwargs["check"]
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(build_inputs.subprocess, "run", run)
    return commands


def test_candidate_prepare_full_flow(tmp_path, monkeypatch):
    archive, data = packet(tmp_path)
    commands = docker_stub(monkeypatch)
    stage = tmp_path / "stage"
    build_inputs.prepare(write_manifest(tmp_path, data), stage, root=tmp_path, archive=archive)
    assert (stage / archive.name).read_bytes() == archive.read_bytes()
    assert json.loads((stage / "candidate-sources.json").read_text()) == data["sources"]
    assert [c[-1] for c in commands[:4]] == [r["local_tag"] for r in data["images"].values()]
    expected = []
    labels = ["haloloom.hyperloom_ref=" + data["sources"]["Hyperloom"]["ref"],
              "haloloom.geak_ref=" + data["sources"]["GEAK"]["ref"],
              "haloloom.haloloom_ref=" + data["sources"]["HaloLoom"]["ref"],
              "haloloom.candidate_id=" + data["version"], "haloloom.promotion_authority=false"]
    for name, row in data["images"].items():
        expected.append(["docker", "pull", row["base_reference"]])
        if row["apply_overlay"]:
            expected.append(["docker", "build", "--network", "none", "--target", name,
                             "--build-arg", "BASE_IMAGE=" + row["base_reference"], "-f",
                             "docker/source-current/Dockerfile", "-t", row["local_tag"],
                             *[arg for label in labels for arg in ("--label", label)], "."])
        else:
            expected.append(["docker", "tag", row["base_reference"], row["local_tag"]])
    assert commands[4:] == expected


@pytest.mark.parametrize("failure", [(0, "[]", ""), (1, "", "Cannot connect to the Docker daemon"),
    (1, "", "unauthorized"), (125, "", "Error response from daemon: No such image: haloloom-aiter-tools:candidate-unique-001\n"),
    (1, "", ""), (1, "", "Error response from daemon: No such image: wrong-tag\n"),
    (1, "", "Error: No such image: haloloom-aiter-tools:candidate-unique-001\nunauthorized")])
def test_all_tags_checked_fail_closed_before_mutation(tmp_path, monkeypatch, failure):
    archive, data = packet(tmp_path)
    commands = docker_stub(monkeypatch, failure=failure)
    stage = tmp_path / "stage"
    with pytest.raises(build_inputs.InputError):
        build_inputs.prepare(write_manifest(tmp_path, data), stage, root=tmp_path, archive=archive)
    assert len(commands) == 4
    assert all(c[:3] == ["docker", "image", "inspect"] for c in commands)
    assert not stage.exists()
    assert not list(tmp_path.glob(".stage.*"))


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(schema_version=2.0), lambda d: d.update(schema_version=True),
    *[lambda d, v=v: d.update(version=v) for v in ("v0.1.1", "candidate-", "candidate-../x", "candidate-a_b", "candidate- a", 2)],
    lambda d: d.update(url="https://example.test/x"),
    lambda d: d["overlay_archive"].update(url="https://user:secret@example.test/candidate.tgz"),
    *[lambda d, v=v: d["overlay_archive"].update(filename=v) for v in ("../x.tgz", "/x.tgz", "x\\y.tgz", "x.zip", "x\n.tgz", "-x.tgz")],
    lambda d: d["overlay_archive"].update(sha256="A" * 64),
    lambda d: d["sources"].pop("GEAK"), lambda d: d["sources"].update(extra={}),
    lambda d: d["sources"]["GEAK"].update(extra="x"),
    *[lambda d, v=v: d["sources"]["Hyperloom"].update(ref=v) for v in ("main", "A" * 40, "a" * 39, 123)],
    lambda d: d["sources"]["HaloLoom"].update(tree="B" * 40),
    lambda d: d["images"]["quark"].update(apply_overlay=False),
    lambda d: d["images"]["vllm"].update(base_reference="local:latest"),
])
def test_candidate_rejects_invalid_manifest(tmp_path, mutate):
    _, data = packet(tmp_path)
    mutate(data)
    with pytest.raises(build_inputs.InputError):
        build_inputs.validate_manifest(data)


@pytest.mark.parametrize("kind", ["missing", "relative", "wrong-name", "symlink", "directory", "fifo", "oversize", "hash", "corrupt", "traversal", "archive-link", "unpacked", "missing-sources", "sources-mismatch", "sources-duplicate", "sources-invalid"])
def test_candidate_bad_archive_fails_before_any_docker(tmp_path, kind):
    archive, data = packet(tmp_path)
    cap = build_inputs.DEFAULT_MAX_BYTES
    if kind == "missing": archive = tmp_path / "absent" / archive.name
    elif kind == "relative": archive = Path(archive.name)
    elif kind == "wrong-name": archive = tmp_path / "other.tgz"; archive.write_bytes(b"x")
    elif kind in {"symlink", "directory", "fifo"}:
        original = archive.rename(tmp_path / "original.tgz")
        if kind == "symlink": archive.symlink_to(original)
        elif kind == "directory": archive.mkdir()
        else: os.mkfifo(archive)
    elif kind == "oversize": cap = archive.stat().st_size - 1
    elif kind == "hash": data["overlay_archive"]["sha256"] = "f" * 64
    else:
        if kind == "corrupt": archive.write_bytes(b"not gzip")
        elif kind == "sources-mismatch": archive, data = packet(tmp_path, sources_raw='{}')
        elif kind == "sources-duplicate": archive, data = packet(tmp_path, sources_raw='{"GEAK": {}, "GEAK": {}}')
        elif kind == "sources-invalid": archive, data = packet(tmp_path, sources_raw='{')
        elif kind == "missing-sources": make_tar(archive, [(tarfile.TarInfo("payload"), b"x")])
        elif kind == "unpacked":
            archive, data = packet(tmp_path, extra=[(tarfile.TarInfo("big"), b"x" * 10000)])
            cap = 2000
        else:
            info = tarfile.TarInfo("../escape" if kind == "traversal" else "link")
            if kind == "archive-link": info.type, info.linkname = tarfile.SYMTYPE, "candidate-sources.json"
            archive, data = packet(tmp_path, extra=[(info, b"")])
        data["overlay_archive"]["sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(build_inputs.InputError):
        build_inputs.prepare(write_manifest(tmp_path, data), tmp_path / "stage", root=tmp_path, archive=archive, max_bytes=cap)
    assert not (tmp_path / "stage").exists()
    assert not list(tmp_path.glob(".stage.*"))


def test_schema2_requires_archive_and_schema1_refuses_it(tmp_path):
    archive, data = packet(tmp_path)
    with pytest.raises(build_inputs.InputError, match="archive"):
        build_inputs.prepare(write_manifest(tmp_path, data), tmp_path / "stage", root=tmp_path)
    with pytest.raises(build_inputs.InputError, match="archive"):
        build_inputs.prepare(write_manifest(tmp_path, manifest(archive)), tmp_path / "stage", root=tmp_path, archive=archive)


@pytest.mark.parametrize("field", ["schema_version", "ref", "filename"])
def test_candidate_manifest_duplicate_keys(tmp_path, field):
    _, data = packet(tmp_path)
    raw = json.dumps(data)
    value = {"schema_version": "2", "ref": json.dumps(data["sources"]["GEAK"]["ref"]), "filename": '"candidate.tgz"'}[field]
    raw = raw.replace(f'"{field}": {value}', f'"{field}": {value}, "{field}": {value}', 1)
    path = tmp_path / "duplicate.json"
    path.write_text(raw)
    with pytest.raises(build_inputs.InputError, match="duplicate JSON key"):
        build_inputs.load_manifest(path)


def test_candidate_cli_through_unchanged_shell(tmp_path, monkeypatch):
    # Execute the actual shell/Python entrypoint with CPU-only subprocess interception.
    monkeypatch.undo()
    archive, data = packet(tmp_path)
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    source = Path(build_inputs.__file__).parent
    for filename in ("build_images.sh", "build_release_inputs.py"):
        shutil.copy2(source / filename, scripts / filename)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "python3").symlink_to(sys.executable)
    (binaries / "dirname").symlink_to(shutil.which("dirname"))
    log = tmp_path / "commands.jsonl"
    hook = tmp_path / "sitecustomize.py"
    hook.write_text(
        'import json,subprocess,urllib.request\nfrom pathlib import Path\n'
        'def forbidden(*a, **k): raise AssertionError("candidate network access")\n'
        'urllib.request.urlopen=forbidden\n'
        'def run(command, **kwargs):\n'
        ' assert command[0]=="docker", command\n'
        ' with Path(' + repr(str(log)) + ').open("a") as f: f.write(json.dumps(command[1:])+"\\n")\n'
        ' if command[1:3]==["image","inspect"]:\n'
        '  return subprocess.CompletedProcess(command,1,"","Error: No such image: "+command[-1]+"\\n")\n'
        ' return subprocess.CompletedProcess(command,0)\n'
        'subprocess.run=run\n'
    )
    result = subprocess.run(["/bin/bash", str(scripts / "build_images.sh"), "--archive", str(archive),
                             "--manifest", str(write_manifest(tmp_path, data))],
                            env={**os.environ, "PATH": str(binaries), "PYTHONPATH": str(tmp_path)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "HALOLOOM_CANDIDATE_BUILD_COMPLETE" in result.stdout
    assert (root / "dist/source-current/candidate-sources.json").is_file()
    commands = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(commands) == 13
    assert all(c[:2] == ["image", "inspect"] for c in commands[:4])
