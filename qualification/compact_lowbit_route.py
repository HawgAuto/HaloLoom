#!/usr/bin/env python3
"""Run the exact async-v7 route gate against a compact golden image."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class CompactRouteError(RuntimeError):
    """The compact image or route artifact is not the sealed runtime."""


def _strict_json(path: Path) -> Any:
    def reject_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CompactRouteError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            path.read_bytes(),
            object_pairs_hook=reject_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise CompactRouteError(f"invalid JSON: {path}") from error


def _file_identity(value: Any, label: str) -> tuple[dict[str, Any], Path]:
    if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"}:
        raise CompactRouteError(f"{label} identity schema is invalid")
    path = Path(value["path"]) if isinstance(value["path"], str) else Path()
    digest = value["sha256"]
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not path.is_file()
        or type(value["bytes"]) is not int
        or value["bytes"] < 0
        or path.stat().st_size != value["bytes"]
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        raise CompactRouteError(f"{label} identity is invalid")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise CompactRouteError(f"{label} binding hash mismatch")
    return dict(value), path


def validate_compact_route(
    path: Path,
    *,
    framework: str,
    quantization: str,
    image_id: str,
) -> dict[str, Any]:
    artifact = _strict_json(path)
    if (
        not isinstance(artifact, Mapping)
        or artifact.get("schema") != "haloloom.gfx1151-lowbit-compact-route.v1"
        or artifact.get("status") != "STATIC_RUNTIME_IDENTITY_MATCH"
        or artifact.get("promotion_authority") is not False
        or artifact.get("claim_limits")
        != {
            "physical_route_qualified": False,
            "performance": False,
            "production_promotion": False,
        }
    ):
        raise CompactRouteError("compact route claim boundary is invalid")
    closures = artifact.get("runtime_closure")
    runtime = closures.get(framework) if isinstance(closures, Mapping) else None
    if not isinstance(runtime, Mapping):
        raise CompactRouteError("framework runtime closure is missing")
    if (
        runtime.get("image_id") != image_id
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
    ):
        raise CompactRouteError("compact image identity mismatch")
    if (
        re.fullmatch(r"sha256:[0-9a-f]{64}", str(runtime.get("golden_image_id", "")))
        is None
    ):
        raise CompactRouteError("golden image identity is invalid")

    before, before_path = _file_identity(
        runtime.get("runtime_identity_before"), "runtime identity before"
    )
    after, after_path = _file_identity(
        runtime.get("runtime_identity_after"), "runtime identity after"
    )
    if (
        before_path.read_bytes() != after_path.read_bytes()
        or before["sha256"] != after["sha256"]
    ):
        raise CompactRouteError("runtime identity changed during compaction")
    _, prune_path = _file_identity(runtime.get("prune_manifest"), "prune manifest")
    prune = _strict_json(prune_path)
    if (
        not isinstance(prune, Mapping)
        or prune.get("target_arch") != "gfx1151"
        or type(prune.get("removed_entry_count")) is not int
        or prune["removed_entry_count"] <= 0
    ):
        raise CompactRouteError("prune manifest is invalid")

    bindings = runtime.get("image_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise CompactRouteError("runtime bindings are missing")
    seen: set[str] = set()
    verified_bindings = []
    for index, binding in enumerate(bindings):
        row, bound_path = _file_identity(binding, f"runtime binding {index}")
        if str(bound_path) in seen:
            raise CompactRouteError("runtime binding is duplicated")
        seen.add(str(bound_path))
        verified_bindings.append(row)

    routes = artifact.get("routes")
    matches = (
        [
            row
            for row in routes
            if isinstance(row, Mapping)
            and row.get("quantization_method") == quantization
        ]
        if isinstance(routes, list)
        else []
    )
    if len(matches) != 1:
        raise CompactRouteError("quantization route is not unique")
    route = {}
    for field in (
        "quantization_method",
        "capability",
        "wire_id",
        "kernel_symbol",
        "module_sha256",
    ):
        value = matches[0].get(field)
        if not isinstance(value, str) or not value:
            raise CompactRouteError(f"route field is invalid: {field}")
        route[field] = value
    if re.fullmatch(r"[0-9a-f]{64}", route["module_sha256"]) is None:
        raise CompactRouteError("route module hash is invalid")

    verified_runtime = dict(runtime)
    verified_runtime["runtime_identity_equal"] = True
    verified_runtime["image_bindings"] = verified_bindings
    return {"route": route, "runtime": verified_runtime}


def _load_v7_runner():
    default = (
        Path(__file__).with_name("validators")
        / "run_rdna35_lowbit_framework_route_v7.py"
    )
    path = Path(os.environ.get("HALOLOOM_V7_ROUTE_TOOL", str(default))).resolve()
    if not path.is_file() or path.is_symlink():
        raise CompactRouteError(f"v7 route tool is invalid: {path}")
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("haloloom_v7_route_runner", path)
    if not spec or not spec.loader:
        raise CompactRouteError(f"cannot load v7 route tool: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    runner = _load_v7_runner()
    runner.__dict__["_route_spec"] = validate_compact_route
    previous = sys.argv
    if argv is not None:
        sys.argv = [previous[0], *argv]
    try:
        return runner.main()
    finally:
        sys.argv = previous


if __name__ == "__main__":
    raise SystemExit(main())
