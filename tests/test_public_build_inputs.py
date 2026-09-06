from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "build_release_inputs.py"
spec = importlib.util.spec_from_file_location("haloloom_build_release_inputs", MODULE_PATH)
assert spec and spec.loader
build_inputs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = build_inputs
spec.loader.exec_module(build_inputs)

NAMES = ("vllm", "sglang", "quark", "aiter-tools")


def manifest(archive: Path, *, digest: str | None = None) -> dict:
    return {
        "schema_version": 1,
        "version": "v0.1.1",
        "overlay_archive": {
            "url": "https://github.com/HawgAuto/HaloLoom/releases/download/v0.1.1/overlay.tar.gz",
            "sha256": digest or hashlib.sha256(archive.read_bytes()).hexdigest(),
            "filename": "overlay.tar.gz",
        },
        "images": {
            name: {
                "base_reference": f"ghcr.io/hawgauto/{name}@sha256:{index:064x}",
                "local_tag": f"haloloom-{name}:v0.1.1-public-build",
                "apply_overlay": name != "aiter-tools",
            }
            for index, name in enumerate(NAMES, 1)
        },
    }


def make_tar(path: Path, entries: list[tuple[tarfile.TarInfo, bytes]]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for info, payload in entries:
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def regular_archive(tmp_path: Path) -> Path:
    path = tmp_path / "overlay.tar.gz"
    directory = tarfile.TarInfo("dist/hyperloom")
    directory.type = tarfile.DIRTYPE
    wheel = tarfile.TarInfo("dist/hyperloom/wheel.whl")
    make_tar(path, [(directory, b""), (wheel, b"wheel")])
    return path


def write_manifest(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "build-inputs.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_validate_manifest_accepts_exact_release_contract(tmp_path: Path) -> None:
    archive = regular_archive(tmp_path)
    assert build_inputs.validate_manifest(manifest(archive))["version"] == "v0.1.1"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(schema_version=2),
        lambda data: data.update(version="v0.1.0"),
        lambda data: data["images"].pop("quark"),
        lambda data: data["images"].update(extra=data["images"]["vllm"]),
        lambda data: data["images"]["vllm"].update(base_reference="ghcr.io/hawgauto/vllm:latest"),
        lambda data: data["images"]["vllm"].update(base_reference="docker.io/hawgauto/vllm@sha256:" + "a" * 64),
        lambda data: data["images"]["vllm"].update(apply_overlay=False),
        lambda data: data["images"]["aiter-tools"].update(apply_overlay=True),
        lambda data: data["images"]["sglang"].update(local_tag=data["images"]["vllm"]["local_tag"]),
        lambda data: data["images"]["sglang"].update(base_reference=data["images"]["vllm"]["base_reference"]),
        lambda data: data["overlay_archive"].update(url="http://example.test/overlay.tar.gz"),
        lambda data: data["overlay_archive"].update(url="https://user:secret@example.test/overlay.tar.gz"),
        lambda data: data["overlay_archive"].update(filename="../overlay.tar.gz"),
        lambda data: data["overlay_archive"].update(sha256="not-a-digest"),
    ],
)
def test_validate_manifest_rejects_invalid_or_ambiguous_inputs(tmp_path: Path, mutate) -> None:
    archive = regular_archive(tmp_path)
    data = manifest(archive)
    mutate(data)
    with pytest.raises(build_inputs.InputError):
        build_inputs.validate_manifest(data)


@pytest.mark.parametrize("duplicate", ["image", "field"])
def test_load_manifest_rejects_duplicate_json_keys(tmp_path: Path, duplicate: str) -> None:
    archive = regular_archive(tmp_path)
    data = manifest(archive)
    raw = json.dumps(data)
    if duplicate == "image":
        row = json.dumps(data["images"]["vllm"])
        raw = raw.replace(f'"images": {{"vllm": {row}', f'"images": {{"vllm": {row}, "vllm": {row}', 1)
    else:
        raw = raw.replace('"apply_overlay": true', '"apply_overlay": true, "apply_overlay": true', 1)
    path = tmp_path / f"duplicate-{duplicate}.json"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(build_inputs.InputError, match="duplicate JSON key"):
        build_inputs.load_manifest(path)


@pytest.mark.parametrize("kind", ["traversal", "absolute", "symlink", "hardlink", "device"])
def test_extract_rejects_unsafe_members(tmp_path: Path, kind: str) -> None:
    archive = tmp_path / "bad.tar.gz"
    info = tarfile.TarInfo("safe")
    if kind == "traversal":
        info.name = "../escape"
    elif kind == "absolute":
        info.name = "/escape"
    elif kind == "symlink":
        info.type, info.linkname = tarfile.SYMTYPE, "target"
    elif kind == "hardlink":
        info.type, info.linkname = tarfile.LNKTYPE, "target"
    elif kind == "device":
        info.type = tarfile.CHRTYPE
    make_tar(archive, [(info, b"")])
    with pytest.raises(build_inputs.InputError):
        build_inputs.extract_archive(archive, tmp_path / "out", 1024)
    assert not (tmp_path / "escape").exists()


def test_extract_enforces_total_unpacked_size_cap(tmp_path: Path) -> None:
    archive = tmp_path / "large.tar.gz"
    make_tar(archive, [(tarfile.TarInfo("payload"), b"12345")])
    with pytest.raises(build_inputs.InputError):
        build_inputs.extract_archive(archive, tmp_path / "out", 4)


def test_prepare_downloads_verifies_extracts_and_runs_only_declared_commands(tmp_path: Path, monkeypatch) -> None:
    source = regular_archive(tmp_path)
    data = manifest(source)
    manifest_path = write_manifest(tmp_path, data)
    stage = tmp_path / "dist" / "source-current"
    commands: list[list[str]] = []

    def fake_download(url: str, destination: Path) -> None:
        assert url == data["overlay_archive"]["url"]
        destination.write_bytes(source.read_bytes())

    def fake_run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(build_inputs, "download_https", fake_download)
    monkeypatch.setattr(build_inputs.subprocess, "run", fake_run)
    build_inputs.prepare(manifest_path, stage, root=Path("/repo"), max_bytes=1024)

    assert (stage / "dist/hyperloom/wheel.whl").read_bytes() == b"wheel"
    assert (stage / "overlay.tar.gz").read_bytes() == source.read_bytes()
    expected: list[list[str]] = []
    for name in NAMES:
        row = data["images"][name]
        expected.append(["docker", "pull", row["base_reference"]])
        if row["apply_overlay"]:
            expected.append([
                "docker", "build", "--network", "none", "--target", name, "--build-arg",
                f"BASE_IMAGE={row['base_reference']}", "-f",
                "docker/source-current/Dockerfile", "-t", row["local_tag"], ".",
            ])
        else:
            expected.append(["docker", "tag", row["base_reference"], row["local_tag"]])
    assert commands == expected


def test_prepare_fails_before_commands_when_digest_mismatches(tmp_path: Path, monkeypatch) -> None:
    source = regular_archive(tmp_path)
    data = manifest(source, digest="f" * 64)
    manifest_path = write_manifest(tmp_path, data)
    monkeypatch.setattr(build_inputs, "download_https", lambda url, destination: destination.write_bytes(source.read_bytes()))
    monkeypatch.setattr(build_inputs.subprocess, "run", lambda *args, **kwargs: pytest.fail("docker must not run"))
    with pytest.raises(build_inputs.InputError, match="SHA-256"):
        build_inputs.prepare(manifest_path, tmp_path / "stage", root=tmp_path, max_bytes=1024)


def test_download_https_uses_bounded_timeout(tmp_path: Path, monkeypatch) -> None:
    timeouts: list[float] = []

    class Response(io.BytesIO):
        def geturl(self) -> str:
            return "https://example.test/overlay.tar.gz"

    def fake_urlopen(request, *, timeout):
        timeouts.append(timeout)
        return Response(b"archive")

    monkeypatch.setattr(build_inputs.urllib.request, "urlopen", fake_urlopen)
    build_inputs.download_https(
        "https://example.test/overlay.tar.gz", tmp_path / "download.tar.gz", max_bytes=1024
    )

    assert timeouts == [build_inputs.DOWNLOAD_TIMEOUT_SECONDS]
    assert 0 < timeouts[0] <= 120


def test_shell_entrypoint_delegates_to_public_input_builder() -> None:
    script = (MODULE_PATH.parent / "build_images.sh").read_text(encoding="utf-8")
    assert 'exec python3 "$ROOT/scripts/build_release_inputs.py" "$@"' in script
    assert "docker build" not in script
    assert "hyperloom-vllm-v027-rocm10" not in script


def test_cli_fails_closed_when_default_manifest_is_missing(tmp_path: Path) -> None:
    isolated_script = tmp_path / "isolated" / "scripts" / MODULE_PATH.name
    isolated_script.parent.mkdir(parents=True)
    shutil.copy2(MODULE_PATH, isolated_script)
    result = subprocess.run(
        [sys.executable, str(isolated_script)], cwd=tmp_path, text=True, capture_output=True
    )
    assert result.returncode != 0
    assert "manifests/build-inputs.json" in result.stderr


def test_cli_rejects_stage_dir_override_before_loading_manifest(tmp_path: Path) -> None:
    isolated_script = tmp_path / "isolated" / "scripts" / MODULE_PATH.name
    isolated_script.parent.mkdir(parents=True)
    shutil.copy2(MODULE_PATH, isolated_script)

    result = subprocess.run(
        [sys.executable, str(isolated_script), "--stage-dir", str(tmp_path / "wrong-stage")],
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "unrecognized arguments: --stage-dir" in result.stderr
    assert "required manifest is missing" not in result.stderr
