#!/usr/bin/env python3
"""Capture deterministic runtime identities before and after image compaction."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def tree_identity(root: Path) -> dict[str, object]:
    root = root.resolve()
    aggregate = hashlib.sha256()
    total = 0
    files = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            digest = hashlib.sha256(
                ("symlink\0" + os.readlink(path)).encode()
            ).hexdigest()
            aggregate.update(
                relative.as_posix().encode() + b"\0" + digest.encode() + b"\n"
            )
        elif path.is_file():
            digest_hash = hashlib.sha256()
            size = 0
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    digest_hash.update(chunk)
                    size += len(chunk)
            digest = digest_hash.hexdigest()
            aggregate.update(
                relative.as_posix().encode() + b"\0" + digest.encode() + b"\n"
            )
            total += size
            files += 1
    return {
        "root": str(root),
        "file_count": files,
        "bytes": total,
        "sha256": aggregate.hexdigest(),
    }


def capture(packages: list[str], paths: dict[str, Path]) -> dict[str, object]:
    package_versions: dict[str, str] = {}
    for name in packages:
        try:
            package_versions[name] = version(name)
        except PackageNotFoundError as error:
            raise RuntimeError(f"required package is not installed: {name}") from error
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze", "--all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    return {
        "schema_version": 1,
        "python": sys.version,
        "executable": sys.executable,
        "packages": package_versions,
        "pip_freeze": sorted(freeze),
        "trees": {label: tree_identity(path) for label, path in sorted(paths.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", action="append", default=[])
    parser.add_argument("--path", action="append", default=[], metavar="LABEL=PATH")
    args = parser.parse_args()

    paths: dict[str, Path] = {}
    for raw in args.path:
        if "=" not in raw:
            raise ValueError(f"--path must be LABEL=PATH: {raw}")
        label, value = raw.split("=", 1)
        if not label or not value:
            raise ValueError(f"--path must be LABEL=PATH: {raw}")
        path = Path(value)
        if not path.is_dir():
            raise ValueError(f"identity path is not a directory: {path}")
        paths[label] = path
    payload = capture(args.package, paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"HALOLOOM_RUNTIME_IDENTITY_OK output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
