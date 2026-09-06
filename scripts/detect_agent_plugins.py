#!/usr/bin/env python3
"""Detect existing host agent CLIs for HaloLoom container plug-ins."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
from pathlib import Path
from typing import TypedDict

_AGENT_ORDER = ("claude", "codex", "hermes")
_AUTO_ORDER = ("codex", "hermes", "claude")


class PluginResult(TypedDict):
    available: list[str]
    selected: str
    env: dict[str, str]


def _find_executable(name: str, path_env: str) -> Path | None:
    candidate = shutil.which(name, path=path_env)
    if not candidate:
        return None
    path = Path(candidate)
    if not os.access(path, os.X_OK):
        return None
    return path.resolve()


def _codex_bundle(root: Path, executable: Path) -> dict[str, object]:
    """Validate the native package layout without executing package code."""
    try:
        metadata = json.loads((root / "codex-package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read Codex bundle metadata: {root}") from exc
    if not isinstance(metadata, dict) or metadata.get("layoutVersion") != 1:
        raise RuntimeError(f"unsupported Codex bundle layout: {root}")
    for field in ("entrypoint", "resourcesDir", "pathDir"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise RuntimeError(f"invalid Codex bundle {field}: {root}")
        relative = Path(value)
        target = (root / relative).resolve()
        if ".." in relative.parts or not target.is_relative_to(root.resolve()):
            raise RuntimeError(f"Codex bundle {field} escapes its runtime root: {root}")
        if field == "entrypoint":
            if (
                target != executable.resolve()
                or not target.is_file()
                or not os.access(target, os.X_OK)
            ):
                raise RuntimeError(
                    f"Codex bundle entrypoint does not match selected executable: {root}"
                )
        elif not target.is_dir():
            raise RuntimeError(f"Codex bundle {field} is missing: {root}")
    helper = root / "bin" / "codex-code-mode-host"
    if not helper.is_file() or not os.access(helper, os.X_OK):
        raise RuntimeError(
            f"Codex bundle helper codex-code-mode-host is missing: {root}"
        )
    return metadata


def _codex_native_executable(executable: Path) -> Path:
    """Resolve a modern npm launcher's exact native package, including hoisted deps.

    The vendor metadata is the mount boundary. Selecting its native executable
    avoids binding only codex.js while omitting a sibling platform package, and
    keeps Code Mode helpers and resources beside the executable inside Docker.
    Legacy/self-contained launchers retain their existing plug-in behavior.
    """
    if executable.suffix != ".js" or executable.parent.name != "bin":
        return executable
    wrapper = executable.parent.parent
    package_file = wrapper / "package.json"
    if not package_file.is_file():
        return executable
    try:
        package = json.loads(package_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"cannot read Codex npm package metadata: {wrapper}"
        ) from exc
    if not isinstance(package, dict) or package.get("name") != "@openai/codex":
        return executable
    machine = platform.machine().lower()
    targets = {
        ("Linux", "x86_64"): ("x86_64-unknown-linux-musl", "linux-x64"),
        ("Linux", "aarch64"): ("aarch64-unknown-linux-musl", "linux-arm64"),
    }
    target = targets.get((platform.system(), machine))
    if target is None:
        return executable
    triple, suffix = target
    dependency = "@openai/codex-" + suffix
    dependencies = package.get("optionalDependencies", {})
    if not isinstance(dependencies, dict) or dependency not in dependencies:
        return executable
    # Match Node's upward node_modules search, including nested and hoisted npm
    # dependencies. Resolve symlinks for pnpm stores before choosing the mount.
    roots = [
        parent / "node_modules" / dependency / "vendor" / triple
        for parent in (wrapper, *wrapper.parents)
        if parent.name != "node_modules"
    ]
    roots.append(wrapper / "vendor" / triple)
    for candidate in roots:
        root = candidate.resolve()
        if not (root / "codex-package.json").is_file():
            continue
        binary = root / "bin" / "codex"
        metadata = _codex_bundle(root, binary)
        if (
            metadata.get("version") != package.get("version")
            or metadata.get("target") != triple
        ):
            raise RuntimeError(f"Codex npm/native bundle identity mismatch: {root}")
        return binary
    # Modern npm distributions that advertise a platform package are unusable
    # unless that exact native dependency is present. Falling back to codex.js
    # would mount only the wrapper and omit sibling helpers/resources.
    raise RuntimeError(f"native Codex bundle not found for {dependency}: {wrapper}")


def _codex_root(executable: Path) -> Path:
    if executable.parent.name == "bin":
        root = executable.parent.parent
        if (root / "codex-package.json").is_file():
            _codex_bundle(root, executable)
            return root
    if executable.suffix == ".js" and executable.parent.name == "bin":
        return executable.parent.parent
    return executable.parent


def _hermes_root(executable: Path) -> Path:
    for parent in executable.parents:
        if parent.name in {"venv", ".venv"}:
            return parent.parent
    return executable.parent


def detect_plugins(
    *,
    path_env: str,
    home: Path,
    state_dir: Path,
    requested: str = "auto",
) -> PluginResult:
    requested = requested.strip().lower() or "auto"
    if requested not in {"auto", *_AGENT_ORDER}:
        raise RuntimeError(
            f"unknown agent {requested!r}; choose auto, claude, codex, or hermes"
        )

    state_dir = state_dir.resolve()
    empty_root = state_dir / "empty"
    empty_root.mkdir(parents=True, exist_ok=True)
    for name in _AGENT_ORDER:
        (empty_root / name).mkdir(exist_ok=True)

    home = home.expanduser().resolve()
    found = {name: _find_executable(name, path_env) for name in _AGENT_ORDER}
    available = [name for name in _AGENT_ORDER if found[name] is not None]
    if not available:
        raise RuntimeError(
            "no supported host agent CLI found on PATH; install or expose one of: "
            "claude, codex, hermes"
        )
    if requested != "auto" and requested not in available:
        raise RuntimeError(f"requested agent {requested!r} is not available on PATH")
    selected = (
        next(name for name in _AUTO_ORDER if name in available)
        if requested == "auto"
        else requested
    )

    claude = found["claude"] if selected == "claude" else None
    codex = found["codex"] if selected == "codex" else None
    if codex is not None:
        codex = _codex_native_executable(codex)
    codex_root = _codex_root(codex) if codex else empty_root / "codex"
    if codex is not None and codex_root.resolve() in {
        home.resolve(),
        home.resolve().parent,
        Path("/"),
    }:
        raise RuntimeError(
            "Codex needs a dedicated installation directory; refusing to mount an entire home or filesystem root"
        )
    hermes = found["hermes"] if selected == "hermes" else None
    config_dirs = {
        "CLAUDE_HOME_HOST": (
            home / ".claude" if selected == "claude" else empty_root / "claude" / "home"
        ),
        "CODEX_HOME_HOST": (
            home / ".codex" if selected == "codex" else empty_root / "codex" / "home"
        ),
        "HERMES_HOME_HOST": (
            home / ".hermes" if selected == "hermes" else empty_root / "hermes" / "home"
        ),
    }
    for directory in config_dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    env = {
        "HALOLOOM_AGENT_PROFILE": selected,
        "HALOLOOM_CLAUDE_ROOT_HOST": str(
            claude.parent if claude else empty_root / "claude"
        ),
        "HALOLOOM_CLAUDE_BIN_HOST": str(
            claude if claude else empty_root / "claude" / "missing"
        ),
        "HALOLOOM_CODEX_ROOT_HOST": str(codex_root),
        "HALOLOOM_CODEX_BIN_HOST": str(
            codex if codex else empty_root / "codex" / "missing"
        ),
        "HALOLOOM_HERMES_ROOT_HOST": str(
            _hermes_root(hermes) if hermes else empty_root / "hermes"
        ),
        "HALOLOOM_HERMES_BIN_HOST": str(
            hermes if hermes else empty_root / "hermes" / "missing"
        ),
        **{name: str(path) for name, path in config_dirs.items()},
    }
    return {"available": available, "selected": selected, "env": env}


def write_env(path: Path, values: dict[str, str]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    output: list[str] = []
    for line in lines:
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in pending:
            key = match.group(1)
            output.append(f"{key}={shlex.quote(pending.pop(key))}")
        else:
            output.append(line)
    if output and output[-1] != "":
        output.append("")
    output.extend(f"{key}={shlex.quote(value)}" for key, value in pending.items())
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--agent", choices=("auto", *_AGENT_ORDER), default="auto")
    args = parser.parse_args()
    result = detect_plugins(
        path_env=os.environ.get("PATH", ""),
        home=Path.home(),
        state_dir=args.state_dir,
        requested=args.agent,
    )
    write_env(args.env_file, result["env"])
    print(
        json.dumps(
            {
                "status": "PASS",
                "available": result["available"],
                "selected": result["selected"],
                "env_file": str(args.env_file.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
