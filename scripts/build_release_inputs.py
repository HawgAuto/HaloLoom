#!/usr/bin/env python3
"""Prepare and build HaloLoom release overlays from immutable public inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
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
    data = _exact_keys(value, {"schema_version", "version", "overlay_archive", "images"}, "manifest")
    if data["schema_version"] != 1 or data["version"] != "v0.1.1":
        raise InputError("manifest must use schema_version 1 and version v0.1.1")

    asset = _exact_keys(data["overlay_archive"], {"url", "sha256", "filename"}, "overlay_archive")
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
        or PurePosixPath(parsed.path).name != filename
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


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise InputError(f"unsafe archive member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise InputError(f"unsafe archive member path: {name!r}")
    return path


def extract_archive(archive_path: Path, destination: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    seen: set[PurePosixPath] = set()
    total = 0
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
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


def prepare(manifest_path: Path, stage: Path, *, root: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    data = load_manifest(manifest_path)
    if max_bytes <= 0:
        raise InputError("size cap must be positive")
    if stage.exists():
        raise InputError(f"refusing to replace existing staging path: {stage}")
    stage.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{stage.name}.", dir=stage.parent))
    try:
        archive_path = temporary / data["overlay_archive"]["filename"]
        download_https(data["overlay_archive"]["url"], archive_path)
        actual = _sha256(archive_path)
        if actual != data["overlay_archive"]["sha256"]:
            raise InputError(f"overlay archive SHA-256 mismatch: expected {data['overlay_archive']['sha256']}, got {actual}")
        extracted = temporary / "contents"
        extract_archive(archive_path, extracted, max_bytes)
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
            else:
                command = ["docker", "tag", row["base_reference"], row["local_tag"]]
            subprocess.run(command, cwd=root, check=True)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("manifests/build-inputs.json"))
    parser.add_argument("--max-unpacked-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    stage = root / "dist/source-current"
    try:
        prepare(manifest_path, stage, root=root, max_bytes=args.max_unpacked_bytes)
    except (InputError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"HALOLOOM_PUBLIC_BUILD_COMPLETE stage={stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
