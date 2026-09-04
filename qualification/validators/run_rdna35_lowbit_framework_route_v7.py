#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run one real vLLM or SGLang low-bit model request in an isolated container."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from rdna35_lowbit_v7_evidence import V7EvidenceError, validate_v7_summary_rows


class FrameworkRouteError(RuntimeError):
    """Raised when a framework route cannot be proven exactly."""


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json_loads(data: str | bytes, label: str) -> Any:
    try:
        return json.loads(
            data,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {value}")
            ),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise FrameworkRouteError(f"invalid {label} JSON") from exc


_EXPECTED_OPERATORS = {
    "gfx1151-fp8-e4m3fnuz": "fp8_e4m3fnuz_f32",
    "gfx1151-mxfp4-e2m1-e8m0": "mxfp4_e2m1_e8m0_f32",
    "gfx1151-w8a8": "w8a8_i32",
    "gfx1151-w4a8": "w4a8_i32",
    "gfx1151-w4a4": "w4a4_i32",
    "gfx1151-w4a16": "w4a16_f32",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hip_module_manifest_identity() -> dict[str, Any]:
    from hyperloom.inference_optimizer.rdna35_lowbit_hip import (
        load_packaged_hip_module_manifest,
    )

    manifest = load_packaged_hip_module_manifest()
    module = Path(manifest.path)
    qualification = Path(manifest.qualification_path)
    manifest_path = module.parent / "module-manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FrameworkRouteError("packaged HIP module manifest is invalid")
    return {
        "schema": manifest.schema,
        "manifest": {
            "path": str(manifest_path),
            "bytes": manifest_path.stat().st_size,
            "sha256": _sha256(manifest_path),
        },
        "module": {
            "path": str(module),
            "bytes": module.stat().st_size,
            "sha256": manifest.sha256,
        },
        "qualification": {
            "path": str(qualification),
            "bytes": qualification.stat().st_size,
            "sha256": manifest.qualification_sha256,
        },
        "code_object_targets": list(manifest.code_object_targets),
        "kernel_symbols": list(manifest.kernel_symbols),
        "abi": list(manifest.abi),
        "block_size": manifest.block_size,
    }


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("xb") as stream:
        stream.write(
            (json.dumps(dict(payload), indent=2, sort_keys=True) + "\n").encode()
        )
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _bound_file_identity(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"}:
        raise FrameworkRouteError(f"runtime closure {label} identity is invalid")
    raw_path = value.get("path")
    path = Path(raw_path) if isinstance(raw_path, str) else Path()
    digest = value.get("sha256")
    size = value.get("bytes")
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not path.is_file()
        or type(size) is not int
        or size < 0
        or path.stat().st_size != size
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or _sha256(path) != digest
    ):
        raise FrameworkRouteError(f"runtime closure {label} identity is invalid")
    return dict(value)


def _route_spec(
    path: Path,
    *,
    framework: str,
    quantization: str,
    image_id: str,
) -> dict[str, Any]:
    artifact = _strict_json_loads(path.read_bytes(), "route artifact")
    if artifact.get("schema") != "hyperloom.gfx1151-lowbit-framework-dispatch.v8":
        raise FrameworkRouteError("route artifact schema is invalid")
    claims = artifact.get("claim_limits")
    if (
        artifact.get("status") != "CPU_BUILT_GPU_UNQUALIFIED"
        or not isinstance(claims, dict)
        or claims.get("real_hip_kernels_preserved") is not True
        or claims.get("request_owned_dispatches_are_asynchronous") is not True
        or claims.get("per_projection_stream_synchronization") is not False
        or claims.get("request_step_event_completion_required") is not True
        or claims.get("gpu_qualified") is not False
        or claims.get("quality_qualified") is not False
        or claims.get("performance_qualified") is not False
        or claims.get("production_deployment_authorized") is not False
        or claims.get("promotion_authority") is not False
    ):
        raise FrameworkRouteError("route artifact claim boundary is invalid")
    if artifact.get("request_admission") != {
        "mode": "openai-api-singleton-until-response-consumed",
        "shared_gpu_batching_claim": False,
    }:
        raise FrameworkRouteError("route artifact admission contract is invalid")
    enqueue = artifact.get("physical_dispatch_receipt")
    expected_enqueue = {
        "schema_version": 3,
        "asynchronous": True,
        "completion_api": "deferred:hipEventRecord+hipEventSynchronize",
        "runtime_id": "ctypes-hip-module:gfx1151:device0:event-boundary-v1",
    }
    completion = artifact.get("request_step_completion_receipt")
    expected_completion = {
        "schema_version": 1,
        "completion_api": "hipEventRecord+hipEventSynchronize",
        "completed": True,
        "scope": "one-framework-scheduler-step-per-distinct-current-stream",
    }
    if enqueue != expected_enqueue or completion != expected_completion:
        raise FrameworkRouteError("route artifact completion contract is invalid")
    closures = artifact.get("runtime_closure")
    runtime = closures.get(framework) if isinstance(closures, Mapping) else None
    if not isinstance(runtime, Mapping):
        raise FrameworkRouteError("framework runtime closure is invalid")
    expected_image_id = runtime.get("image_id")
    if (
        not isinstance(expected_image_id, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_id)
        or image_id != expected_image_id
    ):
        raise FrameworkRouteError("framework image identity mismatch")
    build_identity = _bound_file_identity(runtime.get("build_receipt"), "build receipt")
    readback_identity = _bound_file_identity(
        runtime.get("independent_readback"), "independent readback"
    )
    build_receipt = _strict_json_loads(
        Path(build_identity["path"]).read_bytes(), "build receipt"
    )
    readback = _strict_json_loads(
        Path(readback_identity["path"]).read_bytes(), "independent readback"
    )
    expected_tag = runtime.get("image_tag")
    build_claims = build_receipt.get("claims")
    if (
        build_receipt.get("schema")
        != "hyperloom.rocm10-lowbit-async-v7-derived-image-build.v1"
        or build_receipt.get("status") != "PASS_CPU_BUILD_ONLY"
        or build_receipt.get("framework") != framework
        or build_receipt.get("image", {}).get("id") != expected_image_id
        or build_receipt.get("image", {}).get("tag") != expected_tag
        or not isinstance(build_claims, Mapping)
        or any(build_claims.get(key) is not False for key in (
            "gpu_execution", "numerical_correctness", "quality",
            "performance", "production_readiness",
        ))
        or build_receipt.get("promotion_authority") is not False
        or build_receipt.get("provider_fallback") != "none"
    ):
        raise FrameworkRouteError("framework build receipt boundary is invalid")
    if (
        readback.get("schema")
        != "hyperloom.rocm10-lowbit-async-v7-image-readback.v1"
        or readback.get("status") != "PASS_NO_DEVICE"
        or readback.get("framework") != framework
        or readback.get("image_id") != expected_image_id
        or readback.get("image_tag") != expected_tag
        or readback.get("base_layer_prefix_exact") is not True
        or readback.get("execution")
        != {"network": "none", "gpu_devices_exposed": False}
        or readback.get("promotion_authority") is not False
    ):
        raise FrameworkRouteError("framework image readback boundary is invalid")
    bindings = runtime.get("image_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise FrameworkRouteError("framework image bindings are invalid")
    seen: set[str] = set()
    for index, binding in enumerate(bindings):
        row = _bound_file_identity(binding, f"image binding {index}")
        if row["path"] in seen:
            raise FrameworkRouteError("framework image bindings are duplicated")
        seen.add(row["path"])

    routes = artifact.get("routes")
    if not isinstance(routes, list):
        raise FrameworkRouteError("route artifact is invalid")
    matches = [
        row
        for row in routes
        if isinstance(row, Mapping) and row.get("quantization_method") == quantization
    ]
    if len(matches) != 1:
        raise FrameworkRouteError("quantization route is not unique")
    row = matches[0]
    result = {}
    for field in (
        "quantization_method",
        "capability",
        "wire_id",
        "kernel_symbol",
        "module_sha256",
    ):
        value = row.get(field)
        if not isinstance(value, str) or not value:
            raise FrameworkRouteError(f"route field is invalid: {field}")
        result[field] = value
    if len(result["module_sha256"]) != 64 or any(
        character not in "0123456789abcdef"
        for character in result["module_sha256"]
    ):
        raise FrameworkRouteError("route module_sha256 is invalid")
    return {"route": result, "runtime": dict(runtime)}


def _server_command(
    *,
    framework: str,
    model: Path,
    served_model_name: str,
    quantization: str,
    port: int,
    profile_selected_regions: bool = False,
) -> list[str]:
    if framework == "vllm":
        server_entrypoint = os.environ.get("VLLM_GFX1151_SERVER_ENTRYPOINT")
        if server_entrypoint:
            entrypoint_path = Path(server_entrypoint)
            if (
                not entrypoint_path.is_absolute()
                or entrypoint_path.is_symlink()
                or not entrypoint_path.is_file()
            ):
                raise FrameworkRouteError("vLLM server entrypoint is invalid")
            command = [sys.executable, str(entrypoint_path), "--model", str(model)]
        else:
            command = [
                str(Path(sys.executable).with_name("vllm")),
                "serve",
                str(model),
            ]
        return [
            *command,
            "--served-model-name",
            served_model_name,
            "--quantization",
            quantization,
            "--dtype",
            "bfloat16",
            "--max-model-len",
            "2048",
            "--max-num-batched-tokens",
            "512",
            "--max-num-seqs",
            "1",
            "--tensor-parallel-size",
            "1",
            "--gpu-memory-utilization",
            "0.10",
            "--kv-cache-memory-bytes",
            "2G",
            "--enforce-eager",
            "--no-enable-prefix-caching",
            "--skip-mm-profiling",
            "--generation-config",
            "vllm",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ]
    if framework == "sglang":
        command = [
            sys.executable,
            "-m",
            "sglang.launch_server",
            "--model-path",
            str(model),
            "--served-model-name",
            served_model_name,
            "--quantization",
            quantization,
            "--dtype",
            "bfloat16",
            "--context-length",
            "2048",
            "--max-running-requests",
            "1",
            "--mem-fraction-static",
            "0.10",
            "--disable-cuda-graph",
            "--disable-overlap-schedule",
            "--disable-radix-cache",
            "--attention-backend",
            "triton",
        ]
        if profile_selected_regions:
            # The mandatory VLM startup warmup lazily forks a multimodal CPU
            # worker. ROCProfiler then holds scheduler export waiting for that
            # unrelated child. Selected-region route captures issue their own
            # exact request, so skip only that startup warmup in this lane.
            command.append("--skip-server-warmup")
        command.extend(["--host", "0.0.0.0", "--port", str(port)])
        return command
    raise FrameworkRouteError(f"unsupported framework: {framework}")


def _get_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return _strict_json_loads(response.read(), "HTTP response")


def _get_http_status(url: str, timeout: float = 5.0) -> int:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return int(response.status)


def _post_json(url: str, payload: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(dict(payload)).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return _strict_json_loads(response.read(), "HTTP response")


def _post_profile_control(url: str, timeout: float = 30.0) -> dict[str, Any]:
    request = urllib.request.Request(url, data=b"", method="POST")
    started_ns = time.monotonic_ns()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        status = int(response.status)
    ended_ns = time.monotonic_ns()
    if status != 200:
        raise FrameworkRouteError("profile control request failed")
    return {
        "url": url,
        "http_status": status,
        "response_body": body,
        "start_ns": started_ns,
        "end_ns": ended_ns,
    }


def _request_payload(
    framework: str, served_model_name: str
) -> tuple[dict[str, Any], str]:
    request_identity = f"hyperloom-{framework}-gfx1151-lowbit"
    payload: dict[str, Any] = {
        "model": served_model_name,
        "messages": [{"role": "user", "content": "Reply with exactly: RDNA35_OK"}],
        "temperature": 0.0,
        "max_tokens": 64,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False, "thinking": False},
    }
    if framework == "vllm":
        payload["request_id"] = request_identity
        return payload, f"chatcmpl-{request_identity}"
    if framework == "sglang":
        payload["rid"] = request_identity
        return payload, request_identity
    raise FrameworkRouteError(f"unsupported framework: {framework}")


def _validate_response_request_identity(
    framework: str, response_id: str, expected_response_id: str
) -> str:
    if framework not in {"vllm", "sglang"}:
        raise FrameworkRouteError(f"unsupported framework: {framework}")
    if response_id != expected_response_id:
        raise FrameworkRouteError("response/request identity mismatch")
    return response_id


def _validate_route_request_identity(
    framework: str, response_id: str, rows: Sequence[Mapping[str, Any]]
) -> str:
    request_ids = {row.get("request_id") for row in rows}
    if not request_ids or any(
        not isinstance(request_id, str) or not request_id for request_id in request_ids
    ):
        raise FrameworkRouteError("route/request identity mismatch")
    if framework == "vllm":
        pattern = rf"{re.escape(response_id)}-[0-9a-f]{{8}}"
        matching = {
            request_id
            for request_id in request_ids
            if re.fullmatch(pattern, request_id) is not None
        }
        if len(matching) != 1:
            raise FrameworkRouteError("route/request identity mismatch")
        return next(iter(matching))
    if framework == "sglang":
        if response_id not in request_ids:
            raise FrameworkRouteError("route/request identity mismatch")
        return response_id
    raise FrameworkRouteError(f"unsupported framework: {framework}")


def _wait_ready(
    port: int,
    process: subprocess.Popen[Any],
    timeout: float,
    served_model_name: str,
    *,
    framework: str,
) -> dict[str, Any]:
    if framework not in {"vllm", "sglang"}:
        raise FrameworkRouteError(f"unsupported framework: {framework}")
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise FrameworkRouteError(
                f"server exited before readiness: {process.returncode}"
            )
        try:
            models = _get_json(f"http://127.0.0.1:{port}/v1/models")
            data = models.get("data")
            if isinstance(data, list) and any(
                isinstance(row, Mapping) and row.get("id") == served_model_name
                for row in data
            ):
                # SGLang publishes /v1/models before its mandatory startup
                # warmup has finished.  /health remains 503 while ServerStatus
                # is Starting and becomes 200 only after that internal model
                # request completes.  Starting the selected region earlier
                # would admit the warmup's foreign dispatches.
                if framework == "sglang":
                    health_status = _get_http_status(f"http://127.0.0.1:{port}/health")
                    if health_status != 200:
                        last_error = f"SGLang startup health status {health_status}"
                        time.sleep(1.0)
                        continue
                return models
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(1.0)
    raise FrameworkRouteError(f"server readiness timeout: {last_error}")


def _decode_route_rows(payload: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise FrameworkRouteError("route log is not UTF-8") from exc
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = _strict_json_loads(line, "route log row")
        except FrameworkRouteError as exc:
            raise FrameworkRouteError("route log row is invalid JSON") from exc
        if not isinstance(row, dict):
            raise FrameworkRouteError("route log row is not an object")
        rows.append(row)
    return rows


def _route_delta(path: Path, before: bytes) -> tuple[list[dict[str, Any]], int]:
    after = path.read_bytes() if path.exists() else b""
    if not after.startswith(before):
        raise FrameworkRouteError("route log prefix was rewritten or truncated")
    if before and not before.endswith(b"\n"):
        raise FrameworkRouteError("route log prefix is not line aligned")
    delta = after[len(before) :]
    rows = _decode_route_rows(delta)
    if not rows:
        raise FrameworkRouteError("request emitted no route rows")
    return rows, len(_decode_route_rows(before))


def _descendant_process_tree(
    root_pid: int, *, proc_root: Path = Path("/proc")
) -> list[dict[str, Any]]:
    if type(root_pid) is not int or root_pid <= 0:
        raise FrameworkRouteError("process tree root is invalid")
    processes: dict[int, dict[str, Any]] = {}
    try:
        entries = tuple(proc_root.iterdir())
    except OSError as exc:
        raise FrameworkRouteError("process tree cannot be read") from exc
    for entry in entries:
        if not entry.name.isdigit() or not entry.is_dir():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
            cmdline = (entry / "cmdline").read_bytes()
            stat_line = (entry / "stat").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        values = {}
        for line in status.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key] = value.strip()
        try:
            pid = int(values.get("Pid", ""))
            ppid = int(values.get("PPid", ""))
            argv = [
                value.decode("utf-8", "strict")
                for value in cmdline.split(b"\0")
                if value
            ]
            stat_close = stat_line.rfind(")")
            stat_pid = int(stat_line.split(" ", 1)[0])
            stat_fields = stat_line[stat_close + 2 :].split()
            start_time_ticks = int(stat_fields[19])
        except (IndexError, ValueError, UnicodeError):
            continue
        if (
            pid <= 0
            or ppid < 0
            or not argv
            or pid in processes
            or stat_close <= 0
            or stat_pid != pid
            or start_time_ticks <= 0
        ):
            continue
        processes[pid] = {
            "pid": pid,
            "ppid": ppid,
            "argv": argv,
            "start_time_ticks": start_time_ticks,
        }
    if root_pid not in processes:
        raise FrameworkRouteError("process tree root is missing")
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, row in processes.items():
            if pid not in selected and row["ppid"] in selected:
                selected.add(pid)
                changed = True
    return [processes[pid] for pid in sorted(selected)]


def _merge_process_trees(
    *trees: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for tree in trees:
        for row in tree:
            pid = row.get("pid")
            if type(pid) is not int or pid <= 0:
                raise FrameworkRouteError("process tree row is invalid")
            normalized = dict(row)
            if pid in merged and merged[pid] != normalized:
                raise FrameworkRouteError("process tree identity changed")
            merged[pid] = normalized
    if not merged:
        raise FrameworkRouteError("process tree is empty")
    return [merged[pid] for pid in sorted(merged)]


def _profile_worker_row(
    framework: str, process_tree: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    worker_argv = {
        "vllm": ["VLLM::EngineCore"],
        "sglang": ["sglang::scheduler"],
    }.get(framework)
    matches = [
        dict(row)
        for row in process_tree
        if isinstance(row, Mapping) and row.get("argv") == worker_argv
    ]
    if worker_argv is None or len(matches) != 1:
        raise FrameworkRouteError("worker profile control process identity mismatch")
    worker = matches[0]
    if (
        type(worker.get("pid")) is not int
        or worker["pid"] <= 0
        or type(worker.get("start_time_ticks")) is not int
        or worker["start_time_ticks"] <= 0
    ):
        raise FrameworkRouteError("worker profile control process identity mismatch")
    return worker


def _live_process_identity(
    pid: int, *, proc_root: Path
) -> tuple[list[str], str, int] | None:
    process_dir = proc_root / str(pid)
    try:
        cmdline = (process_dir / "cmdline").read_bytes()
        status = (process_dir / "status").read_text(encoding="utf-8")
        stat_line = (process_dir / "stat").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        raise FrameworkRouteError(
            "profile worker live identity cannot be read"
        ) from exc
    try:
        argv = [
            value.decode("utf-8", "strict") for value in cmdline.split(b"\0") if value
        ]
        stat_close = stat_line.rfind(")")
        stat_pid = int(stat_line.split(" ", 1)[0])
        stat_fields = stat_line[stat_close + 2 :].split()
        stat_state = stat_fields[0]
        start_time_ticks = int(stat_fields[19])
    except (IndexError, ValueError, UnicodeError) as exc:
        raise FrameworkRouteError("profile worker live identity is invalid") from exc
    state = ""
    for line in status.splitlines():
        if line.startswith("State:"):
            state = line.split(":", 1)[1].strip().split(maxsplit=1)[0]
            break
    if (
        (not argv and state != "Z")
        or not state
        or state != stat_state
        or stat_close <= 0
        or stat_pid != pid
        or start_time_ticks <= 0
    ):
        raise FrameworkRouteError("profile worker live identity is invalid")
    return argv, state, start_time_ticks


def _finalize_profile_worker(
    *,
    base_url: str,
    framework: str,
    process_tree: Sequence[Mapping[str, Any]],
    server_log: Path,
    profile_output_dir: Path,
    proc_root: Path = Path("/proc"),
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Request framework-native shutdown and prove worker exit plus export."""

    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
        or not isinstance(base_url, str)
        or not re.fullmatch(r"http://127\.0\.0\.1:\d+", base_url)
    ):
        raise FrameworkRouteError("profile worker finalization input is invalid")
    worker = _profile_worker_row(framework, process_tree)
    pid = worker["pid"]
    expected_argv = worker["argv"]
    expected_start_time = worker["start_time_ticks"]
    identity = _live_process_identity(pid, proc_root=proc_root)
    if (
        identity is None
        or identity[1] == "Z"
        or identity[0] != expected_argv
        or identity[2] != expected_start_time
    ):
        raise FrameworkRouteError("profile worker live identity mismatch")
    if (
        not server_log.is_absolute()
        or server_log.is_symlink()
        or not server_log.is_file()
        or not profile_output_dir.is_absolute()
        or profile_output_dir.is_symlink()
        or not profile_output_dir.is_dir()
    ):
        raise FrameworkRouteError("profile worker profiler export paths are invalid")
    expected_artifacts = tuple(
        sorted(
            (
                profile_output_dir / f"framework-{pid}_kernel_trace.csv",
                profile_output_dir / f"framework-{pid}_agent_info.csv",
            ),
            key=str,
        )
    )
    if any(path.exists() or path.is_symlink() for path in expected_artifacts):
        raise FrameworkRouteError("profile worker profiler artifact already exists")
    control = _post_profile_control(
        f"{base_url}/finalize_profile_worker", timeout=float(timeout)
    )
    deadline = time.monotonic() + float(timeout)
    artifact_identities: list[dict[str, Any]] = []
    while True:
        identity = _live_process_identity(pid, proc_root=proc_root)
        exit_observed = identity is None or identity[1] == "Z"
        if not exit_observed and (
            identity[0] != expected_argv or identity[2] != expected_start_time
        ):
            raise FrameworkRouteError("profile worker live identity changed")
        try:
            log_text = server_log.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise FrameworkRouteError(
                "profile worker profiler export log is invalid"
            ) from exc
        opened = all(
            f"Opened result file: {path}" in log_text for path in expected_artifacts
        )
        generated = (
            f" {pid} simple_timer.cpp:55] [rocprofv3] output generation ::" in log_text
        )
        finalized = (
            f" {pid} simple_timer.cpp:55] [rocprofv3] tool finalization ::" in log_text
        )
        if exit_observed and opened and generated and finalized:
            identities = []
            for path in expected_artifacts:
                if path.is_symlink() or not path.is_file():
                    break
                before = path.stat()
                if before.st_size <= 0:
                    break
                digest = _sha256(path)
                after = path.stat()
                if (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                ) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    break
                identities.append(
                    {"path": str(path), "bytes": after.st_size, "sha256": digest}
                )
            if len(identities) == len(expected_artifacts):
                artifact_identities = identities
                break
        if time.monotonic() >= deadline:
            raise FrameworkRouteError("profile worker shutdown/export timed out")
        time.sleep(0.05)
    return {
        "action": "finalize",
        **control,
        "pid": pid,
        "argv": expected_argv,
        "start_time_ticks": expected_start_time,
        "exit_observed": True,
        "profiler_export_observed": True,
        "profiler_artifacts": artifact_identities,
    }


def _worker_profile_controls(
    server_log: Path,
    *,
    framework: str,
    process_tree: Sequence[Mapping[str, Any]],
    http_controls: Sequence[Mapping[str, Any]],
    expected_library: str,
) -> list[dict[str, Any]]:
    """Bind worker-local ROCTx controls to the controller HTTP transactions."""

    worker_argv = {
        "vllm": ["VLLM::EngineCore"],
        "sglang": ["sglang::scheduler"],
    }.get(framework)
    worker_pids = {
        row.get("pid")
        for row in process_tree
        if isinstance(row, Mapping) and row.get("argv") == worker_argv
    }
    if worker_argv is None or len(worker_pids) != 1:
        raise FrameworkRouteError("worker profile control process identity mismatch")
    worker_pid = next(iter(worker_pids))
    if type(worker_pid) is not int or worker_pid <= 0:
        raise FrameworkRouteError("worker profile control process identity mismatch")
    if len(http_controls) != 2:
        raise FrameworkRouteError("worker profile control HTTP evidence mismatch")

    events: list[dict[str, Any]] = []
    try:
        lines = server_log.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise FrameworkRouteError("worker profile control log is invalid") from exc
    marker = "HYPERLOOM_ROCPROF_SELECTED_REGION"
    expected_fields = {
        "event",
        "action",
        "library",
        "pid",
        "return_code",
        "time_ns",
    }
    for line in lines:
        if marker not in line:
            continue
        start = line.find("{")
        try:
            event = _strict_json_loads(line[start:], "worker profile control event")
        except FrameworkRouteError as exc:
            raise FrameworkRouteError(
                "worker profile control event is invalid"
            ) from exc
        if not isinstance(event, dict) or set(event) != expected_fields:
            raise FrameworkRouteError("worker profile control event is invalid")
        events.append(event)
    if len(events) != 2:
        raise FrameworkRouteError("worker profile control event count mismatch")
    for event, control, action in zip(
        events, http_controls, ("resume", "pause"), strict=True
    ):
        event_time = event.get("time_ns")
        control_start = control.get("start_ns")
        control_end = control.get("end_ns")
        if (
            event.get("event") != marker
            or event.get("action") != action
            or control.get("action") != action
            or event.get("library") != expected_library
            or event.get("pid") != worker_pid
            or event.get("return_code") != 0
            or type(event_time) is not int
            or type(control_start) is not int
            or type(control_end) is not int
            or not control_start <= event_time <= control_end
        ):
            raise FrameworkRouteError("worker profile control event mismatch")
    if events[0]["time_ns"] >= events[1]["time_ns"]:
        raise FrameworkRouteError("worker profile control ordering mismatch")
    return events


def validate_route_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    framework: str,
    route: Mapping[str, str],
    model_revision: str,
    response_id: str,
    minimum_unique_layers: int = 1,
) -> dict[str, Any]:
    contract = dict(route)
    contract["operator"] = _EXPECTED_OPERATORS.get(route.get("quantization_method"))
    try:
        return validate_v7_summary_rows(
            rows,
            framework=framework,
            route=contract,
            model_revision=model_revision,
            response_id=response_id,
            minimum_unique_layers=minimum_unique_layers,
        )
    except V7EvidenceError as exc:
        raise FrameworkRouteError(str(exc)) from exc


def _validate_route_evidence(
    *,
    framework: str,
    response_id: str,
    rows: Sequence[Mapping[str, Any]],
    route: Mapping[str, str],
    model_revision: str,
    minimum_unique_layers: int,
) -> tuple[str, dict[str, Any]]:
    route_request_id = _validate_route_request_identity(framework, response_id, rows)
    selected_count = 0
    for row in rows:
        if row.get("request_id") != route_request_id:
            break
        selected_count += 1
    if selected_count == 0 or any(
        row.get("request_id") == route_request_id for row in rows[selected_count:]
    ):
        raise FrameworkRouteError(
            "exact request route rows are not a contiguous prefix"
        )
    selected_rows = rows[:selected_count]
    foreign_rows = rows[selected_count:]
    summary = validate_route_rows(
        selected_rows,
        framework=framework,
        route=route,
        model_revision=model_revision,
        response_id=route_request_id,
        minimum_unique_layers=minimum_unique_layers,
    )
    summary.update(
        {
            "route_delta_rows": len(rows),
            "foreign_suffix_rows": len(foreign_rows),
            "foreign_suffix_request_ids": sorted(
                {str(row.get("request_id")) for row in foreign_rows}
            ),
        }
    )
    return route_request_id, summary


def _response_identity(
    response: Mapping[str, Any], expected_model: str
) -> tuple[str, str, dict[str, int]]:
    response_id = response.get("id")
    choices = response.get("choices")
    usage = response.get("usage")
    if not isinstance(response_id, str) or not response_id:
        raise FrameworkRouteError("response identity missing")
    if response.get("model") != expected_model:
        raise FrameworkRouteError("response model identity mismatch")
    if not isinstance(choices, list) or len(choices) != 1:
        raise FrameworkRouteError("response choices invalid")
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    if not isinstance(message, Mapping):
        raise FrameworkRouteError("response message invalid")
    text = str(message.get("content") or message.get("reasoning_content") or "").strip()
    if text != "RDNA35_OK":
        raise FrameworkRouteError("response output oracle failed")
    if not isinstance(usage, Mapping):
        raise FrameworkRouteError("response usage missing")
    counters = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(field)
        if type(value) is not int or value <= 0:
            raise FrameworkRouteError(f"invalid token counter: {field}")
        counters[field] = value
    if (
        counters["total_tokens"]
        != counters["prompt_tokens"] + counters["completion_tokens"]
    ):
        raise FrameworkRouteError("token counters are inconsistent")
    return response_id, text, counters


def _record_response_before_validation(
    receipt: dict[str, Any],
    response: Mapping[str, Any],
    *,
    served_model_name: str,
) -> tuple[str, str, dict[str, int]]:
    """Preserve the complete response even when the semantic oracle fails."""

    receipt["response"] = response
    return _response_identity(response, served_model_name)


def _server_stop_mode(
    framework: str, *, profile_enabled: bool, worker_finalized: bool
) -> str:
    if framework == "sglang":
        return "parent-interrupt"
    if framework == "vllm":
        return "parent-term" if profile_enabled and not worker_finalized else "group-term"
    raise FrameworkRouteError("unsupported framework stop mode")


def _stop(process: subprocess.Popen[Any], *, mode: str = "group-term") -> int:
    if mode not in {"group-term", "parent-term", "parent-interrupt"}:
        raise FrameworkRouteError("unsupported server stop mode")
    if process.poll() is None:
        if mode == "parent-interrupt":
            process.send_signal(signal.SIGINT)
        elif mode == "parent-term":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=90 if mode != "group-term" else 60)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=30)
    return int(process.returncode or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--framework", choices=("vllm", "sglang"), required=True)
    parser.add_argument("--quantization", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--served-model-name", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--route-spec", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ready-timeout", type=float, default=900.0)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve(strict=True)
    if any(output_dir.iterdir()):
        raise FrameworkRouteError("output directory must be empty")
    model = args.model.resolve(strict=True)
    route_spec_path = args.route_spec.resolve(strict=True)
    runtime_binding = _route_spec(
        route_spec_path,
        framework=args.framework,
        quantization=args.quantization,
        image_id=os.environ.get("HYPERLOOM_FRAMEWORK_IMAGE_ID", ""),
    )
    route = runtime_binding["route"]
    if len(args.model_revision) != 40 or any(
        c not in "0123456789abcdef" for c in args.model_revision
    ):
        raise FrameworkRouteError("model revision is invalid")

    route_log = Path(
        os.environ.get(f"{args.framework.upper()}_GFX1151_LOWBIT_ROUTE_LOG", "")
    )
    hip_module_identity = _hip_module_manifest_identity()
    if not route_log.is_absolute() or route_log.exists():
        raise FrameworkRouteError("route log must be a new absolute path")
    if (
        os.environ.get(f"{args.framework.upper()}_GFX1151_LOWBIT_MODEL_REVISION")
        != args.model_revision
    ):
        raise FrameworkRouteError("model revision environment mismatch")

    profile_enabled = os.environ.get("HYPERLOOM_ROCPROF_SELECTED_REGIONS") == "1"
    command = _server_command(
        framework=args.framework,
        model=model,
        served_model_name=args.served_model_name,
        quantization=args.quantization,
        port=args.port,
        profile_selected_regions=profile_enabled,
    )
    server_log = output_dir / "server.log"
    receipt_path = output_dir / "route-receipt.json"
    started = time.time()
    process: subprocess.Popen[Any] | None = None
    profile_active = False
    profile_controls: list[dict[str, Any]] = []
    worker_profile_controls: list[dict[str, Any]] = []
    worker_profile_finalization: dict[str, Any] | None = None
    server_work_dir: Path | None = None
    profile_output_dir: Path | None = None
    profile_library: Path | None = None
    if profile_enabled:
        raw_work_dir = os.environ.get("HYPERLOOM_PROFILE_WORK_DIR", "")
        server_work_dir = Path(raw_work_dir)
        raw_output_dir = os.environ.get("HYPERLOOM_PROFILE_OUTPUT_DIR", "")
        profile_output_dir = Path(raw_output_dir)
        raw_profile_library = os.environ.get("HYPERLOOM_ROCPROFILER_ROCTX_LIBRARY", "")
        profile_library = Path(raw_profile_library)
        if (
            not server_work_dir.is_absolute()
            or server_work_dir.is_symlink()
            or not server_work_dir.is_dir()
            or not profile_output_dir.is_absolute()
            or profile_output_dir.is_symlink()
            or not profile_output_dir.is_dir()
            or not profile_library.is_absolute()
            or profile_library.is_symlink()
            or not profile_library.is_file()
        ):
            raise FrameworkRouteError(
                "profile work/output directory or library is invalid"
            )
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL",
        "framework": args.framework,
        "quantization_method": args.quantization,
        "route": route,
        "runtime_closure": runtime_binding["runtime"],
        "model": str(model),
        "model_revision": args.model_revision,
        "served_model_name": args.served_model_name,
        "command": command,
        "started_at_epoch": started,
        "route_spec": {
            "path": str(route_spec_path),
            "bytes": route_spec_path.stat().st_size,
            "sha256": _sha256(route_spec_path),
        },
        "hip_module": hip_module_identity,
        "framework_version": importlib.metadata.version(args.framework),
        "profile_selected_regions": profile_enabled,
        "server_work_dir": str(server_work_dir) if server_work_dir else None,
        "profile_output_dir": str(profile_output_dir) if profile_output_dir else None,
    }
    exit_code = 1
    server_env = os.environ.copy()
    if profile_enabled:
        server_env["HYPERLOOM_PROFILE_SERVER_LOG"] = str(server_log)
    try:
        with server_log.open("xb") as log_stream:
            process = subprocess.Popen(
                command,
                stdout=log_stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=server_env,
                cwd=server_work_dir,
            )
            models = _wait_ready(
                args.port,
                process,
                args.ready_timeout,
                args.served_model_name,
                framework=args.framework,
            )
            ready = time.time()
            before_payload = route_log.read_bytes() if route_log.exists() else b""
            request_payload, expected_response_id = _request_payload(
                args.framework, args.served_model_name
            )
            process_tree_before = _descendant_process_tree(os.getpid())
            if profile_enabled:
                profile_controls.append(
                    {
                        "action": "resume",
                        **_post_profile_control(
                            f"http://127.0.0.1:{args.port}/start_profile"
                        ),
                    }
                )
                profile_active = True
            request_started_monotonic_ns = time.monotonic_ns()
            response = _post_json(
                f"http://127.0.0.1:{args.port}/v1/chat/completions",
                request_payload,
                timeout=300.0,
            )
            request_ended_monotonic_ns = time.monotonic_ns()
            if profile_enabled:
                profile_controls.append(
                    {
                        "action": "pause",
                        **_post_profile_control(
                            f"http://127.0.0.1:{args.port}/stop_profile"
                        ),
                    }
                )
                profile_active = False
            process_tree_after = _descendant_process_tree(os.getpid())
            process_tree = _merge_process_trees(process_tree_before, process_tree_after)
            if profile_enabled:
                if profile_library is None:
                    raise FrameworkRouteError("profile library identity is missing")
                worker_profile_controls = _worker_profile_controls(
                    server_log,
                    framework=args.framework,
                    process_tree=process_tree,
                    http_controls=profile_controls,
                    expected_library=str(profile_library),
                )
            response_id, text, usage = _record_response_before_validation(
                result,
                response,
                served_model_name=args.served_model_name,
            )
            _validate_response_request_identity(
                args.framework, response_id, expected_response_id
            )
            request_rows, route_log_start = _route_delta(route_log, before_payload)
            route_request_id, route_summary = _validate_route_evidence(
                framework=args.framework,
                response_id=response_id,
                rows=request_rows,
                route=route,
                model_revision=args.model_revision,
                minimum_unique_layers=16,
            )
            if profile_enabled:
                if profile_output_dir is None:
                    raise FrameworkRouteError("profile output identity is missing")
                worker_profile_finalization = _finalize_profile_worker(
                    base_url=f"http://127.0.0.1:{args.port}",
                    framework=args.framework,
                    process_tree=process_tree,
                    server_log=server_log,
                    profile_output_dir=profile_output_dir,
                )
            result.update(
                {
                    "status": "PASS",
                    "ready_at_epoch": ready,
                    "models_response": models,
                    "response": response,
                    "response_text": text,
                    "usage": usage,
                    "response_id": response_id,
                    "route_request_id": route_request_id,
                    "request_window": {
                        "clock": "CLOCK_MONOTONIC",
                        "start_ns": request_started_monotonic_ns,
                        "end_ns": request_ended_monotonic_ns,
                    },
                    "server_process_tree": process_tree,
                    "profile_controls": profile_controls,
                    "worker_profile_controls": worker_profile_controls,
                    "worker_profile_finalization": worker_profile_finalization,
                    "route_validation": route_summary,
                    "route_log_start": route_log_start,
                    "route_log_end": route_log_start + route_summary["rows"],
                    "route_log_prefix_bytes": len(before_payload),
                    "route_log_prefix_sha256": hashlib.sha256(
                        before_payload
                    ).hexdigest(),
                }
            )
            exit_code = 0
    except Exception as exc:  # noqa: BLE001 - preserve evidence for unexpected engine failures.
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if profile_active and process is not None and process.poll() is None:
            try:
                profile_controls.append(
                    {
                        "action": "pause-after-error",
                        **_post_profile_control(
                            f"http://127.0.0.1:{args.port}/stop_profile"
                        ),
                    }
                )
                profile_active = False
            except Exception as exc:  # noqa: BLE001 - preserve cleanup failure.
                result["status"] = "FAIL"
                result["profile_cleanup_error"] = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
                exit_code = 1
        result["profile_controls"] = profile_controls
        if process is not None:
            result["server_exit_code"] = _stop(
                process,
                mode=_server_stop_mode(
                    args.framework,
                    profile_enabled=profile_enabled,
                    worker_finalized=worker_profile_finalization is not None,
                ),
            )
        result["completed_at_epoch"] = time.time()
        if server_log.is_file():
            result["server_log"] = {
                "path": str(server_log),
                "bytes": server_log.stat().st_size,
                "sha256": _sha256(server_log),
            }
        if route_log.is_file():
            route_log_identity = {
                "path": str(route_log),
                "bytes": route_log.stat().st_size,
                "sha256": _sha256(route_log),
            }
            result["route_log"] = route_log_identity
            result["route_log_sha256"] = route_log_identity["sha256"]
        try:
            current_hip_module = _hip_module_manifest_identity()
            if current_hip_module != hip_module_identity:
                raise FrameworkRouteError("HIP module identity changed during execution")
        except FrameworkRouteError as exc:
            result["status"] = "FAIL"
            result["error"] = {"type": type(exc).__name__, "message": str(exc)}
            exit_code = 1
        _atomic_json(receipt_path, result)
    print(
        json.dumps(
            {"receipt": str(receipt_path), "status": result["status"]}, sort_keys=True
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

