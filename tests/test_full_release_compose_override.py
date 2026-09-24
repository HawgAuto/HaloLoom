"""Current full-image loader closures, additive to legacy base contracts."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
VLLM_LOADER = (
    "/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/host-math/lib:"
    "/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib:"
    "/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib"
)
SGLANG_LOADER = (
    "/opt/venv/lib/python3.14/site-packages/torch/lib:"
    "/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib:"
    "/opt/rocm/lib/host-math/lib:/opt/rocm/lib/llvm/lib:/opt/rocm/lib"
)


def test_full_release_override_matches_image_specific_loader_closures():
    override = yaml.safe_load((ROOT / "compose.override.yaml").read_text())
    expected = {"vllm": VLLM_LOADER, "quark": VLLM_LOADER, "sglang": SGLANG_LOADER}
    assert set(override) == {"services"}
    assert set(override["services"]) == set(expected)
    for name, loader in expected.items():
        assert override["services"][name] == {"environment": {"LD_LIBRARY_PATH": loader}}
    assert VLLM_LOADER.index("_rocm_sdk_core/lib:") < VLLM_LOADER.index("/opt/rocm/core-10.0/lib")


def test_override_preserves_native_profiler_and_all_other_runtime_settings():
    base = yaml.safe_load((ROOT / "compose.yaml").read_text())
    override = yaml.safe_load((ROOT / "compose.override.yaml").read_text())
    for name, row in override["services"].items():
        before = base["services"][name]["environment"]
        after = {**before, **row["environment"]}
        assert {k: v for k, v in before.items() if k != "LD_LIBRARY_PATH"} == {
            k: v for k, v in after.items() if k != "LD_LIBRARY_PATH"
        }
        assert "HSA_OVERRIDE_GFX_VERSION" not in after
    assert base["services"]["vllm"]["environment"]["ROCP_TOOL_LIBRARIES"].endswith("/torch/lib/libtorch_cpu.so")
    assert "aiter-tools" not in override["services"]
