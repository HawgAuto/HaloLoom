#!/usr/bin/env python3
"""Prune non-gfx1151 ROCm kernel payloads from a staged image root.

The script intentionally touches only known architecture-partitioned stores and
explicit package/build caches. It never searches the filesystem and deletes a
path merely because its name contains ``gfx``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

TARGET_ARCH = "gfx1151"
GENERIC_ARCH_TAGS = frozenset({"gfx11", "gfx115x"})
ARCH_RE = re.compile(r"gfx[0-9][0-9a-z]*", re.IGNORECASE)

STATIC_STORE_SUFFIXES = (
    ".kpack",
    "share/miopen/db",
    "lib/rocblas/library",
    "lib/hipblaslt/library",
)

EXPLICIT_CACHE_PATHS = (
    "root/.cache/pip",
    "opt/cargo",
    "opt/rustup",
    "var/cache/apt/archives",
    "var/lib/apt/lists",
)

RUNTIME_BUILD_PATHS = (
    "opt/vllm-deps",
    "opt/vllm-build",
    "opt/sglang-build",
    "opt/v7",
)

AITER_STORE_SUFFIXES = (
    "aiter/ops/triton/_gluon_kernels",
    "aiter/ops/triton/configs",
    "aiter_meta/csrc/opus_gemm/gen_co",
    "aiter_meta/csrc/opus_gemm/include",
    "aiter_meta/csrc/opus_moe/include",
    "aiter_meta/hsa",
)


@dataclass(frozen=True)
class Removal:
    path: str
    kind: str
    bytes: int
    files: int
    sha256: str
    reason: str


def _site_packages(root: Path) -> list[Path]:
    lib = root / "opt/venv/lib"
    if not lib.is_dir():
        return []
    return sorted(p for p in lib.glob("python*/site-packages") if p.is_dir())


def known_stores(root: Path) -> list[Path]:
    stores = [root / "opt/rocm/core-10.0" / suffix for suffix in STATIC_STORE_SUFFIXES]
    for site in _site_packages(root):
        sdk = site / "_rocm_sdk_libraries"
        stores.extend(sdk / suffix for suffix in STATIC_STORE_SUFFIXES)
        stores.append(site / "torch/.kpack")
        stores.extend(site / suffix for suffix in AITER_STORE_SUFFIXES)
    return sorted({p for p in stores if p.is_dir()})


def explicit_arch_files(root: Path) -> list[Path]:
    roots = [root / "opt/rocm/core-10.0/lib"]
    roots.extend(site / "_rocm_sdk_libraries/lib" for site in _site_packages(root))
    found: list[Path] = []
    for lib in roots:
        if not lib.is_dir():
            continue
        found.extend(lib.glob("libMIOpenCKGroupedConv_gfx*.so"))
        found.extend(lib.glob("librocshmem_device_gfx*.bc"))
    return sorted(p for p in found if p.is_file() or p.is_symlink())


def arch_tags(path: Path) -> set[str]:
    return {match.lower() for match in ARCH_RE.findall(path.name)}


def is_non_target_arch_entry(path: Path) -> bool:
    tags = arch_tags(path)
    if not tags:
        return False
    return TARGET_ARCH not in tags and not tags & GENERIC_ARCH_TAGS


def _path_digest(path: Path) -> tuple[int, int, str]:
    if path.is_symlink():
        target = os.readlink(path)
        return 0, 0, hashlib.sha256(("symlink\0" + target).encode()).hexdigest()
    if path.is_file():
        data_hash = hashlib.sha256()
        total = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                data_hash.update(chunk)
                total += len(chunk)
        return total, 1, data_hash.hexdigest()
    aggregate = hashlib.sha256()
    total = 0
    files = 0
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            rel = item.relative_to(path).as_posix()
            digest = hashlib.sha256(
                ("symlink\0" + os.readlink(item)).encode()
            ).hexdigest()
            aggregate.update(rel.encode() + b"\0" + digest.encode() + b"\n")
        elif item.is_file():
            size, _, digest = _path_digest(item)
            rel = item.relative_to(path).as_posix()
            aggregate.update(rel.encode() + b"\0" + digest.encode() + b"\n")
            total += size
            files += 1
    return total, files, aggregate.hexdigest()


def _assert_under_root(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise RuntimeError(f"refusing path outside staged root: {path}")


def _candidate_entries(root: Path, *, runtime: bool) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    for store in known_stores(root):
        for child in store.iterdir():
            if is_non_target_arch_entry(child):
                candidates.append(
                    (child, f"non-{TARGET_ARCH} precompiled kernel asset")
                )
    for path in explicit_arch_files(root):
        if is_non_target_arch_entry(path):
            candidates.append((path, f"non-{TARGET_ARCH} precompiled device library"))
    for rel in EXPLICIT_CACHE_PATHS:
        path = root / rel
        if path.exists() or path.is_symlink():
            candidates.append((path, "package/build cache"))
    if runtime:
        for rel in RUNTIME_BUILD_PATHS:
            path = root / rel
            if path.exists() or path.is_symlink():
                candidates.append((path, "runtime-unneeded build artifact"))
    dedup: dict[Path, str] = {}
    for path, reason in sorted(candidates, key=lambda row: len(row[0].parts)):
        _assert_under_root(path, root)
        if any(parent in dedup for parent in path.parents):
            continue
        dedup[path] = reason
    return sorted(dedup.items(), key=lambda row: row[0].as_posix())


def prune(root: Path, manifest_path: Path, *, dry_run: bool, runtime: bool) -> dict:
    root = root.resolve()
    _assert_under_root(manifest_path, root)
    removals: list[Removal] = []
    for path, reason in _candidate_entries(root, runtime=runtime):
        size, files, digest = _path_digest(path)
        kind = (
            "symlink" if path.is_symlink() else "directory" if path.is_dir() else "file"
        )
        removals.append(
            Removal(
                path="/" + path.relative_to(root).as_posix(),
                kind=kind,
                bytes=size,
                files=files,
                sha256=digest,
                reason=reason,
            )
        )
        if not dry_run:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()

    retained: list[dict[str, object]] = []
    for store in known_stores(root):
        for child in sorted(store.iterdir()):
            tags = arch_tags(child)
            if TARGET_ARCH in tags or tags & GENERIC_ARCH_TAGS:
                size, files, digest = _path_digest(child)
                retained.append(
                    {
                        "path": "/" + child.relative_to(root).as_posix(),
                        "bytes": size,
                        "files": files,
                        "sha256": digest,
                        "arch_tags": sorted(tags),
                    }
                )

    payload = {
        "schema_version": 1,
        "target_arch": TARGET_ARCH,
        "generic_arch_tags_retained": sorted(GENERIC_ARCH_TAGS),
        "dry_run": dry_run,
        "runtime_profile": runtime,
        "removed_entries": [entry.__dict__ for entry in removals],
        "removed_entry_count": len(removals),
        "removed_file_count": sum(entry.files for entry in removals),
        "removed_bytes": sum(entry.bytes for entry in removals),
        "retained_target_entries": retained,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument(
        "--manifest", type=Path, default=Path("/opt/haloloom/prune-manifest.json")
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="also remove runtime-unneeded build artifacts",
    )
    args = parser.parse_args()
    payload = prune(
        args.root, args.manifest, dry_run=args.dry_run, runtime=args.runtime
    )
    print(
        "HALOLOOM_PRUNE_OK "
        f"entries={payload['removed_entry_count']} files={payload['removed_file_count']} "
        f"bytes={payload['removed_bytes']} dry_run={payload['dry_run']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
