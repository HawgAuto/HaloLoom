"""Regression contract for the qualified vLLM native ROCm profiler startup."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KINETO_CLIENT = "/opt/venv/lib/python3.14/site-packages/torch/lib/libtorch_cpu.so"
QUALIFIED_LOADER = (
    "/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/host-math/lib:"
    "/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib"
)


def test_vllm_starts_with_qualified_native_client_and_loader():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    env = compose["services"]["vllm"]["environment"]
    assert env.get("ROCP_TOOL_LIBRARIES") == KINETO_CLIENT
    assert env["LD_LIBRARY_PATH"] == QUALIFIED_LOADER
    assert "LD_PRELOAD" not in env
    assert "HALO_SDK_TAP_DIR" not in env


def test_vllm_profiler_registration_does_not_change_other_lanes():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert "ROCP_TOOL_LIBRARIES" not in compose["x-rocm-runtime"]
    for name in ("sglang", "quark", "aiter-tools"):
        assert "ROCP_TOOL_LIBRARIES" not in compose["services"][name]["environment"]
