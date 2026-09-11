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


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("manifests/build-inputs.json"))
    parser.add_argument("--archive", type=Path, help="absolute local archive path (required only for schema 2)")
    parser.add_argument("--max-unpacked-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--package-quark-native", action="store_true",
                        help="finish the Quark output with its pinned native extension (used by build_images.sh)")
    args = parser.parse_args(argv)
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
