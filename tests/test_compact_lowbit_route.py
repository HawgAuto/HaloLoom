from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "qualification" / "compact_lowbit_route.py"
spec = importlib.util.spec_from_file_location(
    "haloloom_compact_lowbit_route", MODULE_PATH
)
assert spec and spec.loader
compact = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compact
spec.loader.exec_module(compact)


def _identity(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _fixture(tmp_path: Path) -> tuple[Path, str]:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    binding = tmp_path / "runtime.py"
    prune = tmp_path / "prune.json"
    before.write_text('{"same":true}\n')
    after.write_bytes(before.read_bytes())
    binding.write_text("VALUE = 1\n")
    prune.write_text('{"removed_entry_count":1,"target_arch":"gfx1151"}\n')
    image_id = "sha256:" + "1" * 64
    artifact = {
        "schema": "haloloom.gfx1151-lowbit-compact-route.v1",
        "status": "STATIC_RUNTIME_IDENTITY_MATCH",
        "promotion_authority": False,
        "claim_limits": {
            "physical_route_qualified": False,
            "performance": False,
            "production_promotion": False,
        },
        "runtime_closure": {
            "vllm": {
                "image_id": image_id,
                "image_tag": "haloloom-vllm-full-gfx1151:v0.1.0-rc1",
                "golden_image_id": "sha256:" + "2" * 64,
                "runtime_identity_before": _identity(before),
                "runtime_identity_after": _identity(after),
                "prune_manifest": _identity(prune),
                "image_bindings": [_identity(binding)],
            }
        },
        "routes": [
            {
                "quantization_method": "gfx1151-w4a8",
                "capability": "quant.int4_w4a8_rdna35",
                "wire_id": "gfx1151.w4a8.signed_per_channel_per_token",
                "kernel_symbol": "hyperloom_w4a8_dot4_i32_iu8",
                "module_sha256": "3" * 64,
            }
        ],
    }
    path = tmp_path / "route.json"
    path.write_text(json.dumps(artifact))
    return path, image_id


def test_accepts_identity_equal_compact_runtime(tmp_path: Path) -> None:
    path, image_id = _fixture(tmp_path)
    result = compact.validate_compact_route(
        path,
        framework="vllm",
        quantization="gfx1151-w4a8",
        image_id=image_id,
    )
    assert result["route"]["kernel_symbol"] == "hyperloom_w4a8_dot4_i32_iu8"
    assert result["runtime"]["runtime_identity_equal"] is True


def test_rejects_wrong_image_or_mutated_runtime_file(tmp_path: Path) -> None:
    path, image_id = _fixture(tmp_path)
    try:
        compact.validate_compact_route(
            path,
            framework="vllm",
            quantization="gfx1151-w4a8",
            image_id="sha256:" + "4" * 64,
        )
    except compact.CompactRouteError as error:
        assert "image" in str(error)
    else:
        raise AssertionError("wrong image accepted")

    data = json.loads(path.read_text())
    binding = Path(data["runtime_closure"]["vllm"]["image_bindings"][0]["path"])
    binding.write_text("VALUE = 2\n")
    try:
        compact.validate_compact_route(
            path,
            framework="vllm",
            quantization="gfx1151-w4a8",
            image_id=image_id,
        )
    except compact.CompactRouteError as error:
        assert "binding" in str(error)
    else:
        raise AssertionError("mutated binding accepted")


def test_main_delegates_argv_to_no_argument_v7_main(monkeypatch) -> None:
    observed = []

    class Runner:
        def main(self):
            observed.extend(sys.argv[1:])
            return 7

    runner = Runner()
    monkeypatch.setattr(compact, "_load_v7_runner", lambda: runner)
    assert compact.main(["--framework", "sglang"]) == 7
    assert observed == ["--framework", "sglang"]
