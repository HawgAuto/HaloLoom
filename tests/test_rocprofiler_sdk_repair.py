"""CPU publication contracts; synthetic rows are not GPU evidence."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "profiling/rocprofiler-sdk"
HASH = "9280eae676a8d3d135096a327a2524b2b50a9146b13d850c626e0d8e0e49b7b8"
HEADER = "Correlation_Id Dispatch_Id Agent_Id Queue_Id Process_Id Thread_Id Grid_Size Kernel_Id Kernel_Name Workgroup_Size LDS_Block_Size Scratch_Size VGPR_Count Accum_VGPR_Count SGPR_Count Counter_Name Counter_Value Start_Timestamp End_Timestamp".split()


def test_clock_module_refuses_wrong_sdk_before_dlopen(tmp_path):
    path = RUNTIME / "sdk_clock.py"
    assert path.is_file(), "qualified SDK clock is not packaged"
    spec = importlib.util.spec_from_file_location("repair_clock", path)
    assert spec is not None and spec.loader is not None
    clock = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(clock)
    fake = tmp_path / "wrong.so"
    fake.write_bytes(b"not an SDK")
    setattr(clock, "SDK_PATH", fake)
    with pytest.raises(ValueError, match="identity mismatch"):
        clock.stamp()


@pytest.mark.parametrize("mode", ["valid", "missing", "raw", "hash", "reuse", "boundary", "duplicate", "nan"])
def test_reducer_requires_sdk_clock_and_stable_process(tmp_path, mode):
    reducer = RUNTIME / "reduce_raw_counters.py"
    assert reducer.is_file(), "qualified reducer is not packaged"
    ident = {"pid": 123, "start_ticks": 42}
    sdk = {"source": "rocprofiler_get_timestamp", "clock": "CLOCK_BOOTTIME", "sdk_sha256": HASH, "start_ns": 100, "end_ns": 200}
    req = {"sdk_clock": sdk, "pre_processes": [ident], "post_processes": [ident], "start_monotonic_raw_ns": 10000, "end_monotonic_raw_ns": 10100}
    life = {"schema": "qwen38_metrix_lifecycle.v1", "status": "COMPLETE", "clock": "CLOCK_MONOTONIC_RAW", "server_reaped": True, "server_pid": 123, "request": req}
    row = ["1", "1", "Agent 1", "2", "123", "123", "128", "99", "synthetic_kernel", "128", "0", "0", "8", "0", "16", "OccupancyPercent", "0.25", "110", "120"]
    if mode == "missing": del req["sdk_clock"]
    if mode == "raw": sdk["clock"] = "CLOCK_MONOTONIC_RAW"
    if mode == "hash": sdk["sdk_sha256"] = "0" * 64
    if mode == "reuse": req["post_processes"] = [{"pid": 123, "start_ticks": 43}]
    if mode == "boundary": row[-2] = "99"
    if mode == "nan": row[-3] = "nan"
    (tmp_path / "life.json").write_text(json.dumps(life))
    with (tmp_path / "raw.csv").open("w") as f:
        writer = csv.writer(f); writer.writerow(HEADER); writer.writerow(row)
        if mode == "duplicate": writer.writerow(row)
    output = tmp_path / "result.json"
    run = subprocess.run([sys.executable, str(reducer), "--lifecycle", str(tmp_path / "life.json"), "--raw", str(tmp_path / "raw.csv"), "--output", str(output)], capture_output=True, text=True)
    if mode == "valid":
        assert run.returncode == 0, run.stderr
        assert json.loads(output.read_text())["selected_count"] == 1
    else:
        assert run.returncode != 0
        assert not output.exists()


def test_qualified_patch_is_minimal_and_runtime_payload_is_bound():
    manifest = ROOT / "manifests/rocprofiler-sdk-repair.json"
    assert manifest.is_file(), "repair provenance is not packaged"
    m = json.loads(manifest.read_text())
    assert m["sdk_sha256"] == HASH
    assert m["source_commit"] == "6b0e43f341195e203754e08f850e437ff2fc09f9"
    patch = (ROOT / m["patch"]).read_text()
    assert "+            queue.async_complete();" in patch
    assert not any(line.startswith("-") and not line.startswith("---") for line in patch.splitlines())
    import hashlib
    for path, expected in m["runtime_files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected


def test_offline_build_preserves_services_and_uses_real_target():
    p = ROOT / "docker/rocprofiler-sdk/build-sdk.sh"
    assert p.is_file(), "SDK build recipe is not packaged"
    script = p.read_text()
    assert "--target rocprofiler-sdk-shared-library" in script
    assert "ROCPROFILER_DISABLE" not in script
    assert "ROCPROFILER_UNSAFE" not in script
    assert "cmake --install" not in script
    assert "--force-rpath" in script
