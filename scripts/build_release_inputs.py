#!/usr/bin/env python3
"""Prepare and build HaloLoom release overlays from immutable public inputs."""

from __future__ import annotations

import argparse
import hashlib
import gzip
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

EXPECTED_IMAGES = ("vllm", "sglang", "quark", "aiter-tools")
EXPECTED_OVERLAY = {"vllm": True, "sglang": True, "quark": True, "aiter-tools": False}
DIGEST = re.compile(r"[0-9a-f]{64}")
BASE_REFERENCE = re.compile(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}")
LOCAL_TAG = re.compile(r"[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_][A-Za-z0-9_.-]*")
DEFAULT_MAX_BYTES = 1 << 30
DOWNLOAD_TIMEOUT_SECONDS = 30


class InputError(ValueError):
    """A release input is absent, ambiguous, or unsafe."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise InputError(f"{label} must contain exactly: {', '.join(sorted(keys))}")
    return value


def validate_manifest(value: Any) -> dict[str, Any]:
    schema = value.get("schema_version") if isinstance(value, dict) else None
    if type(schema) is not int or schema not in {1, 2, 3}:
        raise InputError("schema_version must be the integer 1, 2, or 3")
    candidate = schema == 2
    successor = schema == 3
    source_bound = candidate or successor
    keys = {"schema_version", "version", "overlay_archive", "images"}
    data = _exact_keys(value, keys | ({"sources"} if source_bound else set()), "manifest")
    if candidate:
        if not isinstance(data["version"], str) or not re.fullmatch(r"candidate-[A-Za-z0-9][A-Za-z0-9.-]*", data["version"]):
            raise InputError("candidate version must be candidate-<safe alphanumeric/dot/hyphen ID>")
    elif successor:
        if (not isinstance(data["version"], str) or data["version"] == "v0.1.1"
                or not re.fullmatch(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-rc(?:0|[1-9][0-9]*))?", data["version"])):
            raise InputError("public successor version must be vX.Y.Z or vX.Y.Z-rcN, excluding v0.1.1")
    elif data["version"] != "v0.1.1":
        raise InputError("manifest must use schema_version 1 and version v0.1.1")
    if source_bound:
        sources = _exact_keys(data["sources"], {"GEAK", "Hyperloom", "HaloLoom"}, "sources")
        for name, source in sources.items():
            _exact_keys(source, {"ref", "tree"}, f"sources.{name}")
            if any(not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{40}", pin) for pin in source.values()):
                raise InputError(f"sources.{name} ref and tree must be lowercase 40-character Git hashes")

    asset = _exact_keys(data["overlay_archive"], {"sha256", "filename"} | (set() if candidate else {"url"}), "overlay_archive")
    if not candidate:
        if not isinstance(asset["url"], str):
            raise InputError("overlay archive URL must be a string")
        parsed = urllib.parse.urlsplit(asset["url"])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise InputError("overlay archive URL must be credential-free HTTPS")
        if parsed.query or parsed.fragment:
            raise InputError("overlay archive URL must not contain a query or fragment")
    filename = asset["filename"]
    if (
        not isinstance(filename, str)
        or filename in {"", ".", ".."}
        or Path(filename).name != filename
        or "\\" in filename
        or not filename.endswith((".tar.gz", ".tgz"))
        or (source_bound and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.(?:tar\.gz|tgz)", filename))
        or (not candidate and PurePosixPath(parsed.path).name != filename)
    ):
        raise InputError("overlay archive filename must be a matching safe .tar.gz/.tgz basename")
    if not isinstance(asset["sha256"], str) or not DIGEST.fullmatch(asset["sha256"]):
        raise InputError("overlay archive SHA-256 must be 64 lowercase hexadecimal characters")

    images = _exact_keys(data["images"], set(EXPECTED_IMAGES), "images")
    bases: set[str] = set()
    tags: set[str] = set()
    for name in EXPECTED_IMAGES:
        row = _exact_keys(images[name], {"base_reference", "local_tag", "apply_overlay"}, f"images.{name}")
        base, tag, apply_overlay = row["base_reference"], row["local_tag"], row["apply_overlay"]
        if not isinstance(base, str) or not BASE_REFERENCE.fullmatch(base):
            raise InputError(f"images.{name}.base_reference must be a digest-pinned ghcr.io reference")
        if not isinstance(tag, str) or not LOCAL_TAG.fullmatch(tag):
            raise InputError(f"images.{name}.local_tag is not a valid explicit tag")
        if type(apply_overlay) is not bool or apply_overlay is not EXPECTED_OVERLAY[name]:
            raise InputError(f"images.{name}.apply_overlay must be {EXPECTED_OVERLAY[name]}")
        if base in bases or tag in tags:
            raise InputError("base references and local tags must be unique")
        bases.add(base)
        tags.add(tag)
    return data


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        return validate_manifest(
            json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
        )
    except FileNotFoundError as error:
        raise InputError(f"required manifest is missing: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise InputError(f"cannot read valid JSON manifest {path}: {error}") from error


def download_https(url: str, destination: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "HaloLoom-public-build/1"})
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, destination.open("xb") as output:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or final.username or final.password:
                raise InputError("download redirected away from credential-free HTTPS")
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise InputError("overlay archive download exceeds size cap")
                output.write(chunk)
    except InputError:
        raise
    except (OSError, urllib.error.URLError) as error:
        raise InputError(f"overlay archive download failed: {error}") from error


def _require_https_target(url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "\\" in parsed.netloc):
            raise ValueError("unsafe target")
        parsed.port  # Reject malformed port syntax before transport.
    except ValueError as error:
        raise InputError("download target must be credential-free HTTPS") from error


class _SuccessorRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib resolves Location before this hook; check the resolved target
        # before its recursive opener.open can dispatch any transport.
        _require_https_target(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_successor_https(url: str, destination: Path,
                             max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    _require_https_target(url)
    opener = urllib.request.build_opener(_SuccessorRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "HaloLoom-public-build/1"})
    total = 0
    try:
        with opener.open(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            _require_https_target(response.geturl())
            with destination.open("xb") as output:
                while chunk := response.read(min(1024 * 1024, max_bytes - total + 1)):
                    total += len(chunk)
                    if total > max_bytes:
                        raise InputError("overlay archive download exceeds size cap")
                    output.write(chunk)
    except (OSError, urllib.error.URLError) as error:
        raise InputError(f"overlay archive download failed: {error}") from error


# Finite schema-3 structure allowance, independent of payload cap. This includes
# headers, per-entry block rounding, extensions and standard 10240-byte padding.
SUCCESSOR_STRUCTURE_BYTES = 1024 * 1024
SUCCESSOR_METADATA_BYTES = 64 * 1024
SUCCESSOR_MAX_HEADERS = 1024
SUCCESSOR_MAX_EXTENSION_CHAIN = 16


def extract_successor_archive(archive_path: Path, destination: Path,
                              max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Preflight physical tar records before tarfile can interpret extensions.

    Spool bounded decompressed bytes to disk. No extraction destination or payload
    is created until the entire gzip stream and physical structure pass. Legacy
    semantic validation then checks names, types, duplicates and effective sizes.
    """
    if max_bytes <= 0:
        raise InputError("size cap must be positive")
    try:
        with tempfile.TemporaryFile(dir=destination.parent) as raw:
            with gzip.open(archive_path, "rb") as source:
                structure = payload = headers = chain = 0
                def copy_exact(size):
                    while size:
                        chunk = source.read(min(size, 64 * 1024))
                        if not chunk:
                            raise InputError("truncated archive body")
                        raw.write(chunk)
                        size -= len(chunk)

                while True:
                    block = source.read(512)
                    if len(block) != 512:
                        raise InputError("truncated archive header")
                    structure += 512
                    if structure > SUCCESSOR_STRUCTURE_BYTES:
                        raise InputError("archive structural size cap exceeded")
                    raw.write(block)
                    if block == b"\0" * 512:
                        # Consume all trailing gzip data, including concatenated
                        # streams, without allowing an expanding tail exemption.
                        while chunk := source.read(min(64 * 1024, SUCCESSOR_STRUCTURE_BYTES - structure + 1)):
                            structure += len(chunk)
                            if structure > SUCCESSOR_STRUCTURE_BYTES or any(chunk):
                                raise InputError("archive padding/structural size cap exceeded")
                            raw.write(chunk)
                        break
                    headers += 1
                    if headers > SUCCESSOR_MAX_HEADERS:
                        raise InputError("archive member/header count cap exceeded")
                    member = tarfile.TarInfo.frombuf(block, "utf-8", "surrogateescape")
                    if member.size < 0:
                        raise InputError("invalid archive member size")
                    extension = member.type in (tarfile.XHDTYPE, tarfile.XGLTYPE,
                                                 tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK)
                    if extension:
                        chain += 1
                        if member.size > SUCCESSOR_METADATA_BYTES or chain > SUCCESSOR_MAX_EXTENSION_CHAIN:
                            raise InputError("archive metadata size/chain cap exceeded")
                        structure += member.size
                    else:
                        chain = 0
                        if not (member.isreg() or member.isdir()) or (member.isdir() and member.size):
                            raise InputError("unsafe archive member type/size")
                        payload += member.size
                        if payload > max_bytes:
                            raise InputError("overlay archive exceeds unpacked size cap")
                    padding = (-member.size) % 512
                    structure += padding
                    if structure > SUCCESSOR_STRUCTURE_BYTES:
                        raise InputError("archive structural size cap exceeded")
                    copy_exact(member.size + padding)
            raw.seek(0)
            class BoundedTarInfo(tarfile.TarInfo):
                # PAX can change logical offsets. Guard the actual parser too,
                # even if it encounters header-like bytes inside physical data.
                count = metadata = depth = 0

                def _reject_sparse(self, *args):
                    raise InputError("sparse archive metadata is unsupported")

                _proc_gnusparse_00 = _reject_sparse
                _proc_gnusparse_01 = _reject_sparse
                _proc_gnusparse_10 = _reject_sparse

                def _proc_member(self, archive):
                    cls = type(self)
                    cls.count += 1
                    cls.depth += 1
                    try:
                        if cls.count > SUCCESSOR_MAX_HEADERS or cls.depth > SUCCESSOR_MAX_EXTENSION_CHAIN + 1:
                            raise InputError("archive parser member/chain cap exceeded")
                        if self.type in (tarfile.XHDTYPE, tarfile.XGLTYPE,
                                         tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK):
                            cls.metadata += self.size
                            if (self.size < 0 or self.size > SUCCESSOR_METADATA_BYTES
                                    or cls.metadata > SUCCESSOR_STRUCTURE_BYTES):
                                raise InputError("archive parser metadata cap exceeded")
                        elif not (self.isreg() or self.isdir()):
                            raise InputError("unsafe archive member type")
                        return super()._proc_member(archive)
                    finally:
                        cls.depth -= 1

            extract_archive(archive_path, destination, max_bytes,
                            _validated_tar=raw, _tarinfo=BoundedTarInfo)
    except (tarfile.TarError, OSError, EOFError) as error:
        raise InputError(f"cannot safely extract overlay archive: {error}") from error


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise InputError(f"unsafe archive member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise InputError(f"unsafe archive member path: {name!r}")
    return path


def extract_archive(archive_path: Path, destination: Path, max_bytes: int = DEFAULT_MAX_BYTES,
                    *, _validated_tar=None, _tarinfo=tarfile.TarInfo) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[PurePosixPath] = set()
    total = 0
    try:
        with tarfile.open(archive_path if _validated_tar is None else None,
                          mode="r:gz" if _validated_tar is None else "r:",
                          fileobj=_validated_tar, tarinfo=_tarinfo) as archive:
            members = archive.getmembers()
            for member in members:
                relative = _safe_member_name(member.name)
                if relative in seen:
                    raise InputError(f"duplicate archive member: {member.name}")
                seen.add(relative)
                if not (member.isdir() or member.isreg()):
                    raise InputError(f"unsafe archive member type: {member.name}")
                if member.size < 0:
                    raise InputError(f"invalid archive member size: {member.name}")
                if member.isreg():
                    total += member.size
                    if total > max_bytes:
                        raise InputError("overlay archive exceeds unpacked size cap")
            for member in members:
                target = destination.joinpath(*_safe_member_name(member.name).parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise InputError(f"cannot read archive member: {member.name}")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                target.chmod(member.mode & 0o777)
    except (tarfile.TarError, OSError) as error:
        raise InputError(f"cannot safely extract overlay archive: {error}") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_candidate_archive(source: Path, destination: Path, max_bytes: int) -> None:
    """Open without following a final symlink; bound both metadata and actual reads."""
    if not source.is_absolute() or source.name != destination.name:
        raise InputError("candidate archive must be an absolute path with matching basename")
    try:
        # O_NONBLOCK prevents a substituted FIFO from blocking before fstat.
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise InputError("candidate archive must be a regular nonsymlink file")
            if metadata.st_size > max_bytes:
                raise InputError("candidate archive exceeds size cap")
            total = 0
            with destination.open("xb") as output:
                while chunk := stream.read(min(1024 * 1024, max_bytes - total + 1)):
                    total += len(chunk)
                    if total > max_bytes:
                        raise InputError("candidate archive exceeds size cap")
                    output.write(chunk)
    except OSError as error:
        raise InputError(f"cannot copy candidate archive: {error}") from error


def _verify_candidate_sources(extracted: Path, sources: dict[str, Any]) -> None:
    try:
        actual = json.loads((extracted / "candidate-sources.json").read_text(encoding="utf-8"),
                            object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InputError(f"cannot read candidate-sources.json: {error}") from error
    if actual != sources:
        raise InputError("candidate-sources.json does not match manifest sources")


def _require_absent_candidate_tags(data: dict[str, Any], root: Path) -> None:
    for row in data["images"].values():
        tag = row["local_tag"]
        result = subprocess.run(["docker", "image", "inspect", tag], cwd=root,
                                capture_output=True, text=True, check=False)
        if result.returncode == 0:
            raise InputError(f"refusing already-existing candidate image tag: {tag}")
        # Docker CLI versions use either prefix. Any other failure is ambiguous.
        absent = {f"Error: No such image: {tag}", f"Error response from daemon: No such image: {tag}"}
        if result.returncode != 1 or result.stdout.strip() not in {"", "[]"} or result.stderr.strip() not in absent:
            raise InputError(f"cannot establish candidate image tag is absent: {tag}")


def prepare(manifest_path: Path, stage: Path, *, root: Path, max_bytes: int = DEFAULT_MAX_BYTES,
            archive: Path | None = None) -> None:
    data = load_manifest(manifest_path)
    candidate = data["schema_version"] == 2
    source_bound = data["schema_version"] in {2, 3}
    if candidate != (archive is not None):
        raise InputError("--archive is required for schema 2 and is only accepted for schema 2")
    if max_bytes <= 0:
        raise InputError("size cap must be positive")
    if stage.exists():
        raise InputError(f"refusing to replace existing staging path: {stage}")
    stage.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{stage.name}.", dir=stage.parent))
    try:
        archive_path = temporary / data["overlay_archive"]["filename"]
        if candidate:
            _copy_candidate_archive(archive, archive_path, max_bytes)
        elif data["schema_version"] == 3:
            download_successor_https(data["overlay_archive"]["url"], archive_path, max_bytes)
        else:
            download_https(data["overlay_archive"]["url"], archive_path)
        actual = _sha256(archive_path)
        if actual != data["overlay_archive"]["sha256"]:
            raise InputError(f"overlay archive SHA-256 mismatch: expected {data['overlay_archive']['sha256']}, got {actual}")
        extracted = temporary / "contents"
        extractor = extract_successor_archive if data["schema_version"] == 3 else extract_archive
        extractor(archive_path, extracted, max_bytes)
        if source_bound:
            _verify_candidate_sources(extracted, data["sources"])
            _require_absent_candidate_tags(data, root)
        shutil.move(str(archive_path), extracted / archive_path.name)
        os.replace(extracted, stage)
        temporary.rmdir()

        for name in EXPECTED_IMAGES:
            row = data["images"][name]
            subprocess.run(["docker", "pull", row["base_reference"]], cwd=root, check=True)
            if row["apply_overlay"]:
                command = [
                    "docker", "build", "--network", "none", "--target", name, "--build-arg",
                    f"BASE_IMAGE={row['base_reference']}", "-f",
                    "docker/source-current/Dockerfile", "-t", row["local_tag"], ".",
                ]
                if source_bound:
                    labels = {
                        "haloloom.hyperloom_ref": data["sources"]["Hyperloom"]["ref"],
                        "haloloom.geak_ref": data["sources"]["GEAK"]["ref"],
                        "haloloom.haloloom_ref": data["sources"]["HaloLoom"]["ref"],
                        "haloloom.candidate_id": data["version"],
                        "haloloom.promotion_authority": "false",
                    }
                    command[-1:-1] = [arg for key, value in labels.items() for arg in ("--label", f"{key}={value}")]
            else:
                command = ["docker", "tag", row["base_reference"], row["local_tag"]]
            subprocess.run(command, cwd=root, check=True)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def package_quark_native(*, root: Path, tag: str) -> None:
    """Finish a freshly built Quark image without changing its dependency pins."""
    subprocess.run([
        "docker", "build", "--network", "none", "--build-arg",
        f"BASE_IMAGE={tag}", "-f", "docker/quark-native-extension/Dockerfile",
        "-t", tag, ".",
    ], cwd=root, check=True)


def _copy_runtime_bundle(bundle: Path, destination: Path) -> list[str]:
    if not bundle.is_dir() or bundle.is_symlink():
        raise InputError("native sidecar bundle must be a nonsymlink directory")
    if (bundle / "bin/codex").exists():
        raise InputError("native sidecar bundle must not contain duplicate codex executable")
    executables: list[str] = []
    for source in sorted(bundle.rglob("*")):
        if source.is_symlink():
            raise InputError(f"native sidecar bundle contains symlink: {source}")
        relative = source.relative_to(bundle)
        target = destination / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            mode = source.stat().st_mode & 0o777
            target.chmod(mode)
            if mode & 0o111:
                executables.append(relative.as_posix())
        else:
            raise InputError(f"native sidecar bundle contains unsupported file: {source}")
    return executables


def _write_reproducible_tar_gz(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise InputError(f"refusing to replace existing successor archive: {output}")
    with output.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w|") as archive:
            for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
                relative = path.relative_to(source).as_posix()
                info = archive.gettarinfo(str(path), relative)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                if path.is_file():
                    with path.open("rb") as stream:
                        archive.addfile(info, stream)
                elif path.is_dir():
                    archive.addfile(info)
                else:
                    raise InputError(f"successor staging contains unsupported file: {relative}")


def package_native_successor(base_archive: Path, output: Path, *, bundle: Path,
                             binary: Path, source_archive: Path, version: str,
                             source_commit: str) -> dict[str, Any]:
    """Replace the native source/runtime in a predecessor build-input archive."""
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise InputError("native runtime version must be X.Y.Z")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise InputError("native source commit must be a lowercase 40-character Git hash")
    if not binary.is_file() or binary.is_symlink():
        raise InputError("patched native binary must be a regular nonsymlink file")
    if not source_archive.is_file() or source_archive.is_symlink():
        raise InputError("native source archive must be a regular nonsymlink file")
    if version not in source_archive.name or not source_archive.name.endswith(".tar.gz"):
        raise InputError("native source archive filename must bind the runtime version")
    check = subprocess.run([str(binary), "--version"], capture_output=True, text=True,
                           timeout=30, check=False)
    if check.returncode != 0 or check.stdout.strip() != f"codex-cli {version}":
        raise InputError("patched native binary version does not match requested version")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="haloloom-native-successor-", dir=output.parent) as temporary:
        stage = Path(temporary) / "stage"
        extract_successor_archive(base_archive, stage)
        manifest_path = stage / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"),
                                  object_pairs_hook=_reject_duplicate_keys)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise InputError(f"cannot read predecessor payload manifest: {error}") from error

        old_runtime = stage / "native-agent-runtime/codex-amd"
        retained = {}
        for name in ("LICENSE", "NOTICE"):
            path = old_runtime / name
            if path.is_file() and not path.is_symlink():
                retained[name] = path.read_bytes()
        shutil.rmtree(stage / "native-agent-runtime", ignore_errors=True)
        shutil.rmtree(stage / "native-agent-source", ignore_errors=True)
        runtime = stage / "native-agent-runtime/codex-amd"
        runtime.mkdir(parents=True)
        executables = _copy_runtime_bundle(bundle, runtime)
        for name, contents in retained.items():
            target = runtime / name
            if not target.exists():
                target.write_bytes(contents)
                target.chmod(0o644)
        entrypoint = runtime / "bin/codex"
        entrypoint.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(binary, entrypoint)
        entrypoint.chmod(0o755)
        executables = sorted(set(executables) | {"bin/codex"})
        files = {path.relative_to(runtime).as_posix(): _sha256(path)
                 for path in sorted(runtime.rglob("*")) if path.is_file()}

        source_dir = stage / "native-agent-source"
        source_dir.mkdir()
        source_target = source_dir / source_archive.name
        shutil.copyfile(source_archive, source_target)
        source_target.chmod(0o644)
        manifest["native_agent_runtime"] = {
            "entrypoint": "bin/codex", "executable_files": executables,
            "files": files, "path": "native-agent-runtime/codex-amd",
            "source_commit": source_commit, "version": version,
        }
        old_source = manifest.get("native_agent_source", {})
        manifest["native_agent_source"] = {
            "path": f"native-agent-source/{source_archive.name}",
            "sha256": _sha256(source_target), "commit": source_commit,
            "scope": old_source.get("scope", "complete matching Codex source and licenses"),
        }
        top_files = manifest.get("files")
        if not isinstance(top_files, dict):
            raise InputError("predecessor payload manifest files must be an object")
        for name in list(top_files):
            if name.startswith(("native-agent-runtime/", "native-agent-source/")):
                del top_files[name]
        for name, digest_value in files.items():
            top_files[f"native-agent-runtime/codex-amd/{name}"] = digest_value
        top_files[f"native-agent-source/{source_archive.name}"] = _sha256(source_target)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_reproducible_tar_gz(stage, output)
    return {"archive": str(output), "archive_sha256": _sha256(output),
            "archive_bytes": output.stat().st_size,
            "entrypoint_sha256": files["bin/codex"],
            "source_sha256": _sha256(source_archive)}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                            text=True, timeout=120, check=False)
    if result.returncode:
        raise InputError(f"git {' '.join(args)} failed for {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def _validate_component_input(repo: Path, expected_ref: str, expected_tree: str,
                              wheel: Path, wheel_prefix: str) -> None:
    if any(not re.fullmatch(r"[0-9a-f]{40}", value)
           for value in (expected_ref, expected_tree)):
        raise InputError("component ref/tree must be lowercase 40-character Git hashes")
    if not repo.is_dir() or repo.is_symlink():
        raise InputError(f"component repository must be a nonsymlink directory: {repo}")
    if _git(repo, "rev-parse", "HEAD") != expected_ref:
        raise InputError(f"component checkout HEAD mismatch: {repo}")
    if _git(repo, "rev-parse", "HEAD^{tree}") != expected_tree:
        raise InputError(f"component checkout tree mismatch: {repo}")
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise InputError(f"component checkout has tracked changes: {repo}")
    if (not wheel.is_file() or wheel.is_symlink() or
            not wheel.name.startswith(wheel_prefix) or not wheel.name.endswith(".whl")):
        raise InputError(f"component wheel is not the expected regular wheel: {wheel}")


def package_source_current_successor(
    base_archive: Path, output: Path, *, apply_script: Path,
    geak_repo: Path, geak_ref: str, geak_tree: str, geak_wheel: Path,
    hyperloom_repo: Path, hyperloom_ref: str, hyperloom_tree: str,
    hyperloom_wheel: Path,
) -> dict[str, Any]:
    """Replace GEAK/Hyperloom source-current inputs without touching native payloads."""
    _validate_component_input(geak_repo, geak_ref, geak_tree, geak_wheel, "geak-")
    _validate_component_input(hyperloom_repo, hyperloom_ref, hyperloom_tree,
                              hyperloom_wheel, "hyperloom_inference_optimizer-")
    if not apply_script.is_file() or apply_script.is_symlink():
        raise InputError("source-current apply script must be a regular nonsymlink file")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="haloloom-source-current-successor-",
                                     dir=output.parent) as temporary:
        stage = Path(temporary) / "stage"
        extract_successor_archive(base_archive, stage)
        manifest_path = stage / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"),
                                  object_pairs_hook=_reject_duplicate_keys)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise InputError(f"cannot read predecessor payload manifest: {error}") from error
        components = manifest.get("components")
        files = manifest.get("files")
        if not isinstance(components, dict) or not isinstance(files, dict):
            raise InputError("predecessor components/files manifest entries must be objects")

        inputs = {
            "geak": (geak_repo, geak_ref, geak_tree, geak_wheel, "geak.bundle"),
            "hyperloom": (hyperloom_repo, hyperloom_ref, hyperloom_tree,
                          hyperloom_wheel, "hyperloom.bundle"),
        }
        for name, (repo, ref, tree, wheel, transport_name) in inputs.items():
            old = components.get(name)
            if not isinstance(old, dict) or not isinstance(old.get("path"), str):
                raise InputError(f"predecessor component manifest is malformed: {name}")
            for stale in (old.get("transport"), old.get("wheel")):
                if isinstance(stale, str) and (stage / stale).exists():
                    target = stage / stale
                    shutil.rmtree(target) if target.is_dir() else target.unlink()
            transport = stage / transport_name
            subprocess.run(["git", "-C", str(repo), "bundle", "create", str(transport), "HEAD"],
                           timeout=300, check=True)
            heads = _git(repo, "bundle", "list-heads", str(transport)).splitlines()
            if heads != [f"{ref} HEAD"]:
                raise InputError(f"component bundle does not contain exactly the requested HEAD: {name}")
            wheel_target = stage / wheel.name
            if wheel_target.exists() and wheel_target != stage / old.get("wheel", ""):
                raise InputError(f"refusing duplicate component wheel name: {wheel.name}")
            shutil.copyfile(wheel, wheel_target)
            wheel_target.chmod(0o644)
            predecessor_ref = old.get("ref")
            if not isinstance(predecessor_ref, str) or not re.fullmatch(r"[0-9a-f]{40}", predecessor_ref):
                raise InputError(f"predecessor component ref is malformed: {name}")
            components[name] = {
                "base": predecessor_ref, "path": old["path"], "ref": ref,
                "transport": transport_name, "tree": tree, "wheel": wheel.name,
                "wheel_sha256": _sha256(wheel_target),
            }

        shutil.copyfile(apply_script, stage / "apply-and-verify.py")
        (stage / "apply-and-verify.py").chmod(0o755)
        runtime_installer = apply_script.parent / "install_native_agent_runtime.py"
        if not runtime_installer.is_file() or runtime_installer.is_symlink():
            raise InputError("source-current native runtime installer must be a regular nonsymlink file")
        shutil.copyfile(runtime_installer, stage / "install-native-agent-runtime.py")
        (stage / "install-native-agent-runtime.py").chmod(0o755)
        stale_verifier = stage / "verify_ecosystem.py"
        if stale_verifier.exists():
            stale_verifier.unlink()

        candidate_path = stage / "candidate-sources.json"
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"),
                               object_pairs_hook=_reject_duplicate_keys)
        candidate["GEAK"] = {"ref": geak_ref, "tree": geak_tree}
        candidate["Hyperloom"] = {"ref": hyperloom_ref, "tree": hyperloom_tree}
        candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")

        expected = {}
        for relative in _git(hyperloom_repo, "ls-files").splitlines():
            source = hyperloom_repo / relative
            if source.is_file() and not source.is_symlink():
                expected[relative] = _sha256(source)
        (stage / "component-source-reference.json").write_text(json.dumps(
            {"expected": expected, "ref": hyperloom_ref}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")

        files.clear()
        for path in sorted(stage.rglob("*")):
            if path.is_file() and path != manifest_path:
                files[path.relative_to(stage).as_posix()] = _sha256(path)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        _write_reproducible_tar_gz(stage, output)
    return {
        "archive": str(output), "archive_sha256": _sha256(output),
        "archive_bytes": output.stat().st_size,
        "geak_ref": geak_ref, "geak_tree": geak_tree,
        "hyperloom_ref": hyperloom_ref, "hyperloom_tree": hyperloom_tree,
    }


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    # Preserve all legacy entrypoints and packet semantics. Route the new full
    # packet before the legacy parser rejects its prepare-only/image options.
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if not any(x in raw_argv for x in ('--package-native-successor', '--package-source-current-successor')):
        peek = argparse.ArgumentParser(add_help=False)
        peek.add_argument('--manifest', type=Path, default=root / 'manifests/build-inputs.json')
        selection, _ = peek.parse_known_args(raw_argv)
        selected = selection.manifest if selection.manifest.is_absolute() else root / selection.manifest
        if selected.is_file():
            try:
                schema = json.loads(selected.read_text(), object_pairs_hook=_reject_duplicate_keys).get('schema_version')
            except (ValueError, OSError):
                schema = None  # Preserve the legacy parser's error handling.
            if type(schema) is int and schema == 4:
                from build_full_release_inputs import main as full_release_main
                return full_release_main(raw_argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("manifests/build-inputs.json"))
    parser.add_argument("--archive", type=Path, help="absolute local archive path (required only for schema 2)")
    parser.add_argument("--max-unpacked-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--package-quark-native", action="store_true",
                        help="finish the Quark output with its pinned native extension (used by build_images.sh)")
    parser.add_argument("--package-native-successor", action="store_true",
                        help="replace native runtime/source in a predecessor build-input archive")
    parser.add_argument("--package-source-current-successor", action="store_true",
                        help="replace GEAK/Hyperloom source-current inputs in an archive")
    parser.add_argument("--base-archive", type=Path)
    parser.add_argument("--native-bundle", type=Path)
    parser.add_argument("--native-binary", type=Path)
    parser.add_argument("--native-source-archive", type=Path)
    parser.add_argument("--native-version")
    parser.add_argument("--native-source-commit")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-current-apply", type=Path)
    parser.add_argument("--geak-repo", type=Path)
    parser.add_argument("--geak-ref")
    parser.add_argument("--geak-tree")
    parser.add_argument("--geak-wheel", type=Path)
    parser.add_argument("--hyperloom-repo", type=Path)
    parser.add_argument("--hyperloom-ref")
    parser.add_argument("--hyperloom-tree")
    parser.add_argument("--hyperloom-wheel", type=Path)
    args = parser.parse_args(argv)
    if args.package_native_successor and args.package_source_current_successor:
        parser.error("successor packaging modes are mutually exclusive")
    if args.package_source_current_successor:
        values = (args.base_archive, args.output, args.source_current_apply,
                  args.geak_repo, args.geak_ref, args.geak_tree, args.geak_wheel,
                  args.hyperloom_repo, args.hyperloom_ref, args.hyperloom_tree,
                  args.hyperloom_wheel)
        if any(value is None for value in values):
            parser.error("source-current successor packaging requires all source-current arguments")
        try:
            result = package_source_current_successor(
                args.base_archive, args.output, apply_script=args.source_current_apply,
                geak_repo=args.geak_repo, geak_ref=args.geak_ref,
                geak_tree=args.geak_tree, geak_wheel=args.geak_wheel,
                hyperloom_repo=args.hyperloom_repo, hyperloom_ref=args.hyperloom_ref,
                hyperloom_tree=args.hyperloom_tree, hyperloom_wheel=args.hyperloom_wheel,
            )
        except (InputError, subprocess.CalledProcessError, OSError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.package_native_successor:
        values = (args.base_archive, args.native_bundle, args.native_binary,
                  args.native_source_archive, args.native_version,
                  args.native_source_commit, args.output)
        if any(value is None for value in values):
            parser.error("native successor packaging requires all --base/native/output arguments")
        try:
            result = package_native_successor(
                args.base_archive, args.output, bundle=args.native_bundle,
                binary=args.native_binary, source_archive=args.native_source_archive,
                version=args.native_version, source_commit=args.native_source_commit,
            )
        except (InputError, subprocess.CalledProcessError, OSError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    stage = root / "dist/source-current"
    try:
        prepare(manifest_path, stage, root=root, max_bytes=args.max_unpacked_bytes, archive=args.archive)
        if args.package_quark_native:
            data = load_manifest(manifest_path)
            package_quark_native(root=root, tag=data["images"]["quark"]["local_tag"])
    except (InputError, subprocess.CalledProcessError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    kind = "CANDIDATE" if args.archive is not None else "PUBLIC"
    print(f"HALOLOOM_{kind}_BUILD_COMPLETE stage={stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
