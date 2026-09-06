#!/usr/bin/env python3
"""Run one HaloLoom serving container while holding the shared GPU lease."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LOCK_PATH = Path("/run/lock/hermes-vllm-gfx1151.lock")


def child_environment(source: Mapping[str, str]) -> dict[str, str]:
    env = dict(source)
    env.pop("HSA_OVERRIDE_GFX_VERSION", None)
    return env


def _validate_extra(service: str, extra: list[str]) -> None:
    if service != "sglang":
        return
    forbidden = (
        "--attention-backend",
        "--prefill-attention-backend",
        "--decode-attention-backend",
        "--enable-cuda-graph",
        "--disable-cuda-graph",
    )
    for argument in extra:
        if any(
            argument == flag or argument.startswith(flag + "=") for flag in forbidden
        ):
            raise ValueError(
                f"extra argument {argument!r} conflicts with the qualified SGLang route"
            )


def _selected_quantization(extra: list[str]) -> str | None:
    values: list[str] = []
    for index, argument in enumerate(extra):
        if argument == "--quantization":
            if index + 1 >= len(extra) or extra[index + 1].startswith("-"):
                raise ValueError("--quantization requires a value")
            values.append(extra[index + 1])
        elif argument.startswith("--quantization="):
            values.append(argument.split("=", 1)[1])
    if len(values) > 1 or any(not value for value in values):
        raise ValueError("quantization must be specified exactly once")
    return values[0] if values else None


def build_command(
    service: str,
    model: str,
    extra: list[str],
    *,
    max_model_len: int,
    model_revision: str | None = None,
) -> list[str]:
    if service not in {"vllm", "sglang"}:
        raise ValueError(f"unsupported service: {service}")
    if not model or model.startswith("-"):
        raise ValueError("model must be a non-option model ID or absolute path")
    if max_model_len <= 0:
        raise ValueError("max_model_len must be positive")
    if extra and extra[0] == "--":
        extra = extra[1:]
    _validate_extra(service, extra)
    quantization = _selected_quantization(extra)
    lowbit = bool(quantization and quantization.startswith("gfx1151-"))
    if lowbit and (
        not isinstance(model_revision, str)
        or re.fullmatch(r"[0-9a-f]{40}", model_revision) is None
    ):
        raise ValueError(
            "low-bit serving requires a lowercase 40-character model revision"
        )

    command = ["docker", "compose", "run", "--rm", "--service-ports"]
    if lowbit:
        revision_variable = (
            "VLLM_GFX1151_LOWBIT_MODEL_REVISION"
            if service == "vllm"
            else "SGLANG_GFX1151_LOWBIT_MODEL_REVISION"
        )
        command.extend(
            [
                "--env",
                "HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1",
                "--env",
                f"{revision_variable}={model_revision}",
            ]
        )
    command.append(service)
    if service == "vllm":
        command.extend(
            [
                "--model",
                model,
                "--trust-remote-code",
                "--max-model-len",
                str(max_model_len),
            ]
        )
        if model_revision:
            command.extend(["--revision", model_revision])
    else:
        command.extend(
            [
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--model-path",
                model,
                "--trust-remote-code",
                "--context-length",
                str(max_model_len),
                "--mem-fraction-static",
                "0.5",
                "--disable-radix-cache",
                "--attention-backend",
                "triton",
                "--disable-cuda-graph",
                "--weight-loader-disable-mmap",
                "--model-loader-extra-config",
                '{"enable_multithread_load":false}',
            ]
        )
        if model_revision:
            command.extend(["--revision", model_revision])
    command.extend(extra)
    return command


def _load_preflight() -> Any:
    path = Path(__file__).with_name("preflight.py")
    spec = importlib.util.spec_from_file_location("haloloom_live_preflight", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load preflight module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_cli(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("vllm", "sglang"))
    parser.add_argument("model")
    parser.add_argument(
        "--max-model-len",
        type=int,
        default=int(os.environ.get("HALOLOOM_MAX_MODEL_LEN", "4096")),
    )
    parser.add_argument("--model-revision")
    if "--" in argv:
        boundary = argv.index("--")
        args = parser.parse_args(argv[:boundary])
        args.extra = argv[boundary + 1 :]
    else:
        args, args.extra = parser.parse_known_args(argv)
    return args


def main() -> int:
    args = parse_cli()

    command = build_command(
        args.service,
        args.model,
        args.extra,
        max_model_len=args.max_model_len,
        model_revision=args.model_revision,
    )
    environment = child_environment(os.environ)
    if "HSA_OVERRIDE_GFX_VERSION" in os.environ:
        print(
            "WARN: removing HSA_OVERRIDE_GFX_VERSION from the serving environment",
            file=sys.stderr,
        )

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        preflight = _load_preflight()
        probe = preflight.live_probe()
        probe["lock_available"] = True  # this process owns it
        probe["hsa_override"] = None  # child_environment removes it
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
