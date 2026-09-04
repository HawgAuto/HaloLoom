#!/usr/bin/env python3
"""Fail-closed verifier for the HaloLoom turnkey ecosystem layer."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

COMPONENT_ROOT = Path("/opt/haloloom/components")
EXPECTED_REFS = {
    "Hyperloom": "a94191bfe0b548a44113e0d28c432d1bff0e3f9f",
    "Magpie": "f25176b855aad86e38ac06442f2a5d2b8e4da21f",
    "TraceLens": "a59a9c165bb64c7c416fd7cf79149803d552e43c",
    "GEAK": "b4dea3fa33ef438d4233aae0ed2c2f425c4e419a",
    "IntelliKit": "2f61453a779980b00504ea3b772ff4a1a1c3f4ad",
    "InferenceX": "3d5581562f643f9bdeb8410cd924e2c70906c966",
}
EXPECTED_FRAMEWORK_REFS = {
    "vllm": "6ddd7a77a256e90f86c108eeed4ce46602cf9657",
    "sglang": "cb9e016cb33b98bc804a57bc70b8272d8e8d134c",
}
REQUIRED_IMPORTS = (
    "hyperloom",
    "kernelforge",
    "Magpie",
    "TraceLens",
    "geak",
    "metrix",
    "ray",
)
REQUIRED_COMMANDS = (
    "inference_optimizer",
    "quantization-agent",
    "kernelforge",
    "magpie",
    "metrix",
    "TraceLens_generate_perf_report_pytorch_inference",
)


def _git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def verify() -> dict[str, object]:
    errors: list[str] = []
    refs: dict[str, str] = {}
    for name, expected in EXPECTED_REFS.items():
        path = COMPONENT_ROOT / name
        if not (path / ".git").is_dir():
            errors.append(f"missing exact source checkout: {path}")
            continue
        actual = _git_head(path)
        refs[name] = actual
        if actual != expected:
            errors.append(f"{name} HEAD mismatch: {actual} != {expected}")

    framework_root = Path("/opt/haloloom/framework-source")
    for name, expected in EXPECTED_FRAMEWORK_REFS.items():
        path = framework_root / name
        if not (path / ".git").is_dir():
            errors.append(f"missing exact framework source checkout: {path}")
            continue
        actual = _git_head(path)
        refs[name] = actual
        if actual != expected:
            errors.append(f"{name} HEAD mismatch: {actual} != {expected}")

    imports: dict[str, bool] = {}
    for name in REQUIRED_IMPORTS:
        available = importlib.util.find_spec(name) is not None
        imports[name] = available
        if not available:
            errors.append(f"missing import: {name}")

    commands: dict[str, str | None] = {}
    for name in REQUIRED_COMMANDS:
        resolved = shutil.which(name)
        commands[name] = resolved
        if not resolved:
            errors.append(f"missing command: {name}")

    runner = COMPONENT_ROOT / "GEAK" / "interface" / "run_e2e.py"
    if not runner.is_file():
        errors.append(f"missing GEAK e2e runner: {runner}")

    metrix_backend = COMPONENT_ROOT / "IntelliKit" / "metrix" / "src" / "metrix" / "backends" / "gfx1151.py"
    if not metrix_backend.is_file():
        errors.append(f"missing IntelliKit gfx1151 backend: {metrix_backend}")

    try:
        hyperloom_version = version("hyperloom-inference-optimizer")
    except Exception as exc:  # pragma: no cover - verifier failure path
        hyperloom_version = None
        errors.append(f"missing Hyperloom distribution metadata: {exc}")
    if hyperloom_version != "1.0.0":
        errors.append(f"Hyperloom version mismatch: {hyperloom_version!r}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "target": "gfx1151",
        "hyperloom_version": hyperloom_version,
        "refs": refs,
        "imports": imports,
        "commands": commands,
        "geak_runner": str(runner),
        "intellikit_gfx1151_backend": str(metrix_backend),
        "errors": errors,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
