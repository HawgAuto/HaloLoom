#!/usr/bin/env python3
"""Detect existing host agent CLIs for HaloLoom container plug-ins."""

from __future__ import annotations

import argparse
import json
import os
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


def _codex_root(executable: Path) -> Path:
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
        "HALOLOOM_CODEX_ROOT_HOST": str(
            _codex_root(codex) if codex else empty_root / "codex"
        ),
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
    parser.add_argument(
        "--agent", choices=("auto", *_AGENT_ORDER), default="auto"
    )
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
