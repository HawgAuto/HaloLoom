#!/usr/bin/env python3
"""Run Hyperloom's original Quark workflow under the shared GPU lease."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

LOCK_PATH = Path("/run/lock/hermes-vllm-gfx1151.lock")
PROVIDERS = frozenset({"claude", "codex", "hermes"})
WORKSPACE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def resolve_provider(requested: str | None, env_file: Path) -> str:
    selected = ""
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            key, separator, value = raw.partition("=")
            if separator and key.strip() == "HALOLOOM_AGENT_PROFILE":
                parsed = shlex.split(value, comments=True, posix=True)
                if len(parsed) != 1:
                    raise ValueError("invalid HALOLOOM_AGENT_PROFILE in .env")
                selected = parsed[0].strip().lower()
                break
    if selected not in PROVIDERS:
        raise ValueError("HaloLoom agent is not configured; run ./scripts/install.sh")
    if requested and requested != selected:
        raise ValueError(
            f"provider {requested!r} is not the installed plug-in {selected!r}; "
            f"rerun ./scripts/install.sh --agent {requested}"
        )
    return selected


def build_command(
    *,
    provider: str,
    prompt: str,
    workspace: str,
    model_id: str | None,
    extra: list[str],
) -> list[str]:
    if provider not in PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    if not WORKSPACE_RE.fullmatch(workspace):
        raise ValueError(
            "workspace must be one relative name using letters, digits, dot, dash or underscore"
        )
    if extra and extra[0] == "--":
        extra = extra[1:]
    command = [
        "docker",
        "compose",
        "run",
        "--rm",
        "-e",
        "HALOLOOM_PARENT_GPU_LOCK=1",
        "quark",
        "--provider",
        provider,
        "--prompt",
        prompt,
        "--workspace",
        f"/workspace/{workspace}",
        "--interactive",
        "off",
    ]
    if model_id:
        command.extend(["--model-id", model_id])
    command.extend(extra)
    return command


def _load_preflight() -> Any:
    path = Path(__file__).with_name("preflight.py")
    spec = importlib.util.spec_from_file_location("haloloom_quantize_preflight", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load preflight module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=sorted(PROVIDERS))
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--model-id")
    parser.add_argument("extra", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    try:
        provider = resolve_provider(
            args.provider, Path(__file__).resolve().parents[1] / ".env"
        )
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    command = build_command(
        provider=provider,
        prompt=args.prompt,
        workspace=args.workspace,
        model_id=args.model_id,
        extra=args.extra,
    )
    environment = dict(os.environ)
    if environment.pop("HSA_OVERRIDE_GFX_VERSION", None) is not None:
        print(
            "WARN: removing HSA_OVERRIDE_GFX_VERSION from the Quark environment",
            file=sys.stderr,
        )

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        preflight = _load_preflight()
        probe = preflight.live_probe()
        probe["lock_available"] = True
        probe["hsa_override"] = None
        report = preflight.assess(probe, allow_busy=False)
        if not report["passed"]:
            for error in report["errors"]:
                print(f"ERROR: {error}", file=sys.stderr)
            return 2
        print("HALOLOOM_GPU_LEASE_ACQUIRED", LOCK_PATH, flush=True)
        print("EXEC", shlex.join(command), flush=True)
        try:
            result = subprocess.run(command, env=environment, check=False)
        except KeyboardInterrupt:
            return 130
        finally:
            print("HALOLOOM_GPU_LEASE_RELEASED", LOCK_PATH, flush=True)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
