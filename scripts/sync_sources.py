#!/usr/bin/env python3
"""Materialize HaloLoom's pinned public source components."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_COMPONENTS = (
    "hyperloom",
    "magpie",
    "intellikit",
    "tracelens",
    "geak",
    "inferencex",
    "lowbit_kernel_pack",
)
BUILD_COMPONENTS = ("vllm", "sglang", "quark", "aiter")
DESTINATIONS = {
    "hyperloom": "Hyperloom",
    "magpie": "Magpie",
    "intellikit": "IntelliKit",
    "tracelens": "TraceLens",
    "geak": "GEAK",
    "inferencex": "InferenceX",
    "lowbit_kernel_pack": "Strix-Halo-Lowbit-Kernel-Pack",
    "vllm": "vLLM",
    "sglang": "SGLang",
    "quark": "Quark",
    "aiter": "AITER",
}


@dataclass(frozen=True)
class Component:
    name: str
    repository: str
    commit: str


def selected_components(
    manifest: dict[str, Any], *, include_build_sources: bool
) -> list[Component]:
    names = DEFAULT_COMPONENTS + (BUILD_COMPONENTS if include_build_sources else ())
    selected: list[Component] = []
    rows = manifest.get("components", {})
    for name in names:
        row = rows.get(name, {})
        repository = row.get("repository")
        commit = row.get("commit")
        if not isinstance(repository, str) or not repository.startswith(
            "https://github.com/"
        ):
            continue
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            continue
        selected.append(Component(name, repository, commit))
    return selected


def clone_commands(component: Component, destination: Path) -> list[list[str]]:
    return [
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            component.repository,
            str(destination),
        ],
        ["git", "-C", str(destination), "checkout", "--detach", component.commit],
    ]


def _run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(command, text=True, capture_output=capture, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{detail}"
        )
    return result.stdout.strip() if capture else ""


def sync_component(component: Component, destination: Path) -> dict[str, str]:
    if destination.exists():
        if not (destination / ".git").exists():
            raise RuntimeError(f"refusing non-Git destination: {destination}")
        status = _run(
            ["git", "-C", str(destination), "status", "--porcelain"], capture=True
        )
        if status:
            raise RuntimeError(f"refusing dirty source checkout: {destination}")
        remote = _run(
            ["git", "-C", str(destination), "remote", "get-url", "origin"], capture=True
        )
        normalized = remote.removesuffix(".git")
        if normalized != component.repository.removesuffix(".git"):
            raise RuntimeError(
                f"origin mismatch for {component.name}: expected {component.repository}, got {remote}"
            )
        _run(
            [
                "git",
                "-C",
                str(destination),
                "fetch",
                "--filter=blob:none",
                "origin",
                component.commit,
            ]
        )
        _run(["git", "-C", str(destination), "checkout", "--detach", component.commit])
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        for command in clone_commands(component, destination):
            _run(command)
    actual = _run(["git", "-C", str(destination), "rev-parse", "HEAD"], capture=True)
    if actual != component.commit:
        raise RuntimeError(
            f"commit mismatch for {component.name}: {actual} != {component.commit}"
        )
    if _run(["git", "-C", str(destination), "status", "--porcelain"], capture=True):
        raise RuntimeError(f"source checkout became dirty: {destination}")
    return {
        "name": component.name,
        "repository": component.repository,
        "commit": actual,
        "path": str(destination.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "manifests/components.json",
    )
    parser.add_argument("--root", type=Path, default=Path("components"))
    parser.add_argument("--include-build-sources", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    selected = selected_components(
        manifest, include_build_sources=args.include_build_sources
    )
    expected = len(DEFAULT_COMPONENTS) + (
        len(BUILD_COMPONENTS) if args.include_build_sources else 0
    )
    if len(selected) != expected:
        raise RuntimeError(
            f"manifest selected {len(selected)} components; expected {expected}"
        )
    rows = [
        sync_component(component, args.root / DESTINATIONS[component.name])
        for component in selected
    ]
    lock = args.root / "source-lock.json"
    lock.write_text(
        json.dumps({"schema_version": 1, "sources": rows}, indent=2, sort_keys=True)
        + "\n"
    )
    print(f"HALOLOOM_SOURCES_OK count={len(rows)} lock={lock.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
