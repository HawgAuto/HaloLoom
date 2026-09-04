# SPDX-License-Identifier: MIT
"""Fail-closed validators for asynchronous V7 request-step evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class V7EvidenceError(ValueError):
    pass


def _fail(message: str) -> None:
    raise V7EvidenceError(message)


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _shape(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(_positive_int(item) for item in value)
    )


def _validate_physical(
    physical: Any,
    *,
    framework: str,
    route: Mapping[str, Any],
    expected_index: int,
    shape_set: set[tuple[int, int, int]],
) -> None:
    if not isinstance(physical, Mapping):
        _fail("physical dispatch sample is not an object")
    shape = physical.get("shape")
    if not _shape(shape) or tuple(shape) not in shape_set:
        _fail("physical dispatch sample shape mismatch")
    expected_grid = [(shape[0] * shape[1] + 63) // 64, 1, 1]
    expected_tp = {
        "kind": "replicated",
        "rank": 0,
        "world_size": 1,
        "global_shape": [shape[1], shape[2]],
        "local_offset": [0, 0],
        "output_reduction_required": False,
    }
    if (
        physical.get("schema_version") != 3
        or not isinstance(physical.get("adapter_id"), str)
        or not str(physical["adapter_id"]).startswith(f"hip-module:{framework}:")
        or physical.get("dispatch_index") != expected_index
        or physical.get("runtime_id")
        != "ctypes-hip-module:gfx1151:device0:event-boundary-v1"
        or physical.get("module_sha256") != route.get("module_sha256")
        or physical.get("code_object_target") != "gfx1151"
        or physical.get("kernel_symbol") != route.get("kernel_symbol")
        or physical.get("grid") != expected_grid
        or physical.get("block") != [64, 1, 1]
        or type(physical.get("stream_address")) is not int
        or int(physical["stream_address"]) < 0
        or physical.get("asynchronous") is not True
        or physical.get("completion_api")
        != "deferred:hipEventRecord+hipEventSynchronize"
        or physical.get("fallback_used") is not False
        or physical.get("tensor_parallel") != expected_tp
    ):
        _fail("physical dispatch sample identity mismatch")


def _validate_streams(
    streams: Any,
    *,
    first: int,
    last: int,
    dispatches: int,
) -> int:
    if not isinstance(streams, list) or not streams:
        _fail("request stream completion list is invalid")
    addresses: list[int] = []
    indexes: list[int] = []
    completion_events = 0
    for stream in streams:
        if not isinstance(stream, Mapping):
            _fail("request stream completion is not an object")
        address = stream.get("stream_address")
        count = stream.get("dispatches")
        stream_first = stream.get("dispatch_index_first")
        stream_last = stream.get("dispatch_index_last")
        completion = stream.get("completion")
        if (
            type(address) is not int
            or address < 0
            or not _positive_int(count)
            or not _positive_int(stream_first)
            or not _positive_int(stream_last)
            or stream_last < stream_first
            or not isinstance(completion, Mapping)
        ):
            _fail("request stream completion identity is invalid")
        completion_indexes = completion.get("dispatch_indexes")
        if (
            not isinstance(completion_indexes, list)
            or len(completion_indexes) != count
            or any(not _positive_int(value) for value in completion_indexes)
            or completion_indexes != sorted(set(completion_indexes))
            or completion_indexes[0] != stream_first
            or completion_indexes[-1] != stream_last
            or completion.get("schema_version") != 1
            or not _positive_int(completion.get("completion_index"))
            or completion.get("runtime_id")
            != "ctypes-hip-module:gfx1151:device0:event-boundary-v1"
            or completion.get("stream_address") != address
            or completion.get("completion_api")
            != "hipEventRecord+hipEventSynchronize"
            or completion.get("completed") is not True
        ):
            _fail("request event completion receipt mismatch")
        addresses.append(address)
        indexes.extend(completion_indexes)
        completion_events += 1
    if addresses != sorted(set(addresses)):
        _fail("request stream identities are duplicate or unordered")
    if len(indexes) != dispatches or sorted(indexes) != list(range(first, last + 1)):
        _fail("request event completion does not close every dispatch")
    return completion_events


def validate_v7_summary_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    framework: str,
    route: Mapping[str, Any],
    model_revision: str,
    response_id: str,
    minimum_unique_layers: int = 1,
) -> dict[str, Any]:
    if framework not in {"vllm", "sglang"} or not rows:
        _fail("V7 route summary input is invalid")
    if not isinstance(response_id, str) or not response_id:
        _fail("V7 route response identity is invalid")
    expected_operator = route.get("operator")
    layer_counts: Counter[str] = Counter()
    shapes: set[tuple[int, int, int]] = set()
    first_sequence: int | None = None
    previous_sequence: int | None = None
    previous_time_ns = 0
    previous_dispatch = 0
    physical_dispatches = 0
    completion_events = 0
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or row.get("schema_version") != 2
            or row.get("evidence_kind") != "request_step_completion"
            or row.get("status") != "PASS"
            or row.get("framework") != framework
            or row.get("request_id") != response_id
            or row.get("model_revision") != model_revision
            or row.get("request_owned") is not True
            or row.get("operator") != expected_operator
            or row.get("quantization_method") != route.get("quantization_method")
            or any(row.get(field) != route.get(field) for field in ("capability", "wire_id", "kernel_symbol"))
        ):
            _fail("V7 route summary identity mismatch")
        sequence = row.get("trace_sequence")
        time_ns = row.get("time_ns")
        if (
            not _positive_int(sequence)
            or not _positive_int(time_ns)
            or (previous_sequence is not None and sequence != previous_sequence + 1)
            or time_ns <= previous_time_ns
        ):
            _fail("V7 route summary sequence is invalid")
        if first_sequence is None:
            first_sequence = sequence
        previous_sequence = sequence
        previous_time_ns = time_ns
        count = row.get("physical_dispatches")
        first = row.get("dispatch_index_first")
        last = row.get("dispatch_index_last")
        if (
            not _positive_int(count)
            or row.get("asynchronous_enqueues") != count
            or row.get("fallback_dispatches") != 0
            or not _positive_int(first)
            or not _positive_int(last)
            or last - first + 1 != count
            or (previous_dispatch and first != previous_dispatch + 1)
        ):
            _fail("V7 dispatch range is invalid")
        layer_names = row.get("layer_names")
        layer_hash = row.get("layer_names_sha256")
        minimum = row.get("layer_invocations_min")
        maximum = row.get("layer_invocations_max")
        shape_rows = row.get("shape_set")
        if (
            not isinstance(layer_names, list)
            or not layer_names
            or layer_names != sorted(set(layer_names))
            or any(not isinstance(name, str) or not name for name in layer_names)
            or layer_hash != _hash_json(layer_names)
            or not _positive_int(minimum)
            or maximum != minimum
            or not isinstance(shape_rows, list)
            or not shape_rows
            or shape_rows != sorted(shape_rows)
            or any(not _shape(shape) for shape in shape_rows)
            or row.get("shape_set_sha256") != _hash_json(shape_rows)
        ):
            _fail("V7 layer or shape summary is invalid")
        shape_set = {tuple(shape) for shape in shape_rows}
        samples = row.get("physical_samples")
        if not isinstance(samples, Mapping) or set(samples) != {"first", "last"}:
            _fail("V7 physical samples are invalid")
        _validate_physical(
            samples["first"],
            framework=framework,
            route=route,
            expected_index=first,
            shape_set=shape_set,
        )
        _validate_physical(
            samples["last"],
            framework=framework,
            route=route,
            expected_index=last,
            shape_set=shape_set,
        )
        completion_events += _validate_streams(
            row.get("streams"), first=first, last=last, dispatches=count
        )
        for name in layer_names:
            layer_counts[name] += minimum
        shapes.update(shape_set)
        physical_dispatches += count
        previous_dispatch = last
    if len(layer_counts) < minimum_unique_layers:
        _fail("V7 route layer coverage is incomplete")
    return {
        "rows": len(rows),
        "unique_layers": len(layer_counts),
        "unique_shapes": [list(shape) for shape in sorted(shapes)],
        "request_id": response_id,
        "first_trace_sequence": first_sequence,
        "last_trace_sequence": previous_sequence,
        "layer_invocations": dict(sorted(layer_counts.items())),
        "physical_dispatches": physical_dispatches,
        "completion_events": completion_events,
        "dispatch_index_min": rows[0]["dispatch_index_first"],
        "dispatch_index_max": previous_dispatch,
        "module_sha256": route.get("module_sha256"),
        "physical_receipt_schema_version": 3,
        "completion_api": "hipEventRecord+hipEventSynchronize",
        "asynchronous": True,
    }


__all__ = ["V7EvidenceError", "validate_v7_summary_rows"]
