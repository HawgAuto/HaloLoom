"""Install or verify the hash-bound native CLI in a new image.

The outer source-current manifest authenticates this specification and payload.
No host credentials, host npm installation, or GPU access is needed.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("invalid runtime path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsafe runtime path: {value}")
    return Path(*path.parts)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_set(root):
    if root.is_symlink():
        raise ValueError(f"runtime symlink: {root}")
    if not root.is_dir():
        raise FileNotFoundError(root)
    files = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"runtime symlink: {path}")
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise ValueError(f"unsupported runtime file type: {path}")
    return files


def validate(root, files):
    if file_set(root) != set(files):
        raise ValueError("runtime file set differs: missing or undeclared file")
    for name, expected in files.items():
        if digest(root / safe_relative(name)) != expected:
            raise ValueError(f"runtime digest mismatch: {name}")


def install_runtime(payload_root, spec, destination, *, verify_only=False):
    payload_root = Path(payload_root)
    destination = Path(destination)
    relative = safe_relative(spec["path"])
    source = payload_root / relative
    files = spec["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("runtime file manifest is empty")
    for name, expected in files.items():
        safe_relative(name)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"invalid runtime digest: {name}")
    executables = set(spec["executable_files"])
    entrypoint = safe_relative(spec["entrypoint"])
    if not executables.issubset(files) or entrypoint.as_posix() not in executables:
        raise ValueError("runtime entrypoint/executable file set is invalid")
    commit = spec["source_commit"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid source commit")
    version = spec["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("invalid runtime version")
    for path in (source, *source.parents, destination, *destination.parents):
        if path.is_symlink():
            raise ValueError(f"runtime symlink in path: {path}")
    validate(source, files)
    if not verify_only:
        if destination.exists() and file_set(destination) != set(files):
            raise ValueError("installed runtime has an unexpected file set")
        destination.mkdir(parents=True, exist_ok=True)
        for name in files:
            target = destination / safe_relative(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / safe_relative(name), target)
            target.chmod(0o755 if name in executables else 0o644)
    validate(destination, files)
    for name in executables:
        if not (destination / name).stat().st_mode & 0o111:
            raise ValueError(f"runtime executable permission missing: {name}")
    check = subprocess.run([str(destination / entrypoint), "--version"],
                           capture_output=True, text=True, timeout=30)
    if check.returncode != 0 or version not in check.stdout:
        raise ValueError(f"native CLI version check failed: {check.returncode}")
    return {"source_commit": commit, "version": version,
            "files_verified": len(files), "entrypoint_sha256": files[entrypoint.as_posix()]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/opt/haloloom/source-current"))
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if Path("/dev/kfd").exists():
        raise RuntimeError("native runtime installation/verification requires no GPU")
    manifest = json.loads((args.root / "manifest.json").read_text())
    result = install_runtime(args.root, manifest["native_agent_runtime"],
                             Path("/opt/haloloom/codex-amd"), verify_only=args.verify_only)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
