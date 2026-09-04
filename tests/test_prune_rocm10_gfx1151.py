from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "prune_rocm10_gfx1151.py"
spec = importlib.util.spec_from_file_location("haloloom_prune", MODULE_PATH)
assert spec and spec.loader
prune_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prune_mod
spec.loader.exec_module(prune_mod)


def _write(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _fixture(root: Path) -> dict[str, Path]:
    sdk = root / "opt/rocm/core-10.0"
    site = root / "opt/venv/lib/python3.14/site-packages"
    paths = {
        "sdk_target": _write(sdk / ".kpack/blas_lib_gfx1151.kpack", b"target"),
        "sdk_other": _write(sdk / ".kpack/blas_lib_gfx942.kpack", b"other"),
        "sdk_generic": _write(sdk / ".kpack/metadata.kpack", b"generic"),
        "rocblas_target": _write(
            sdk / "lib/rocblas/library/gfx1151/kernel.co", b"target-co"
        ),
        "rocblas_other": _write(
            sdk / "lib/rocblas/library/gfx950/kernel.co", b"other-co"
        ),
        "hipblas_target": _write(
            sdk / "lib/hipblaslt/library/gfx1151/kernel.co", b"target-hip"
        ),
        "hipblas_other": _write(
            sdk / "lib/hipblaslt/library/gfx90a/kernel.co", b"other-hip"
        ),
        "miopen_other": _write(sdk / "share/miopen/db/gfx1030.kdb", b"other-db"),
        "miopen_lib_target": _write(
            sdk / "lib/libMIOpenCKGroupedConv_gfx1151.so", b"target-lib"
        ),
        "miopen_lib_other": _write(
            sdk / "lib/libMIOpenCKGroupedConv_gfx1100.so", b"other-lib"
        ),
        "torch_target": _write(
            site / "torch/.kpack/torch_gfx1151.kpack", b"target-torch"
        ),
        "torch_other": _write(
            site / "torch/.kpack/torch_gfx1200.kpack", b"other-torch"
        ),
        "aiter_target": _write(
            site / "aiter_meta/hsa/gfx1151/kernel.co", b"target-aiter"
        ),
        "aiter_other": _write(site / "aiter_meta/hsa/gfx950/kernel.co", b"other-aiter"),
        "aiter_config_target": _write(
            site / "aiter/ops/triton/configs/gfx1151/triton/op/DEFAULT.json",
            b"target-config",
        ),
        "aiter_config_other": _write(
            site / "aiter/ops/triton/configs/gfx942/triton/op/DEFAULT.json",
            b"other-config",
        ),
        "outside": _write(root / "srv/unrelated/gfx950/keep.co", b"outside"),
        "pip_cache": _write(root / "root/.cache/pip/wheel.bin", b"cache"),
        "runtime_build": _write(root / "opt/vllm-build/vllm.whl", b"wheel"),
    }
    return paths


def test_prune_removes_only_allowlisted_non_target_assets(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    manifest = tmp_path / "opt/haloloom/prune.json"

    result = prune_mod.prune(tmp_path, manifest, dry_run=False, runtime=True)

    for name in (
        "sdk_other",
        "rocblas_other",
        "hipblas_other",
        "miopen_other",
        "miopen_lib_other",
        "torch_other",
        "aiter_other",
        "aiter_config_other",
        "pip_cache",
        "runtime_build",
    ):
        assert not paths[name].exists(), name
    for name in (
        "sdk_target",
        "sdk_generic",
        "rocblas_target",
        "hipblas_target",
        "miopen_lib_target",
        "torch_target",
        "aiter_target",
        "aiter_config_target",
        "outside",
    ):
        assert paths[name].exists(), name
    assert result["target_arch"] == "gfx1151"
    assert result["removed_entry_count"] > 0
    assert result["removed_bytes"] > 0
    assert manifest.is_file()
    assert any(
        row["path"].endswith("blas_lib_gfx1151.kpack")
        for row in result["retained_target_entries"]
    )


def test_dry_run_records_without_deleting(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    manifest = tmp_path / "opt/haloloom/dry-run.json"

    result = prune_mod.prune(tmp_path, manifest, dry_run=True, runtime=True)

    assert result["dry_run"] is True
    assert all(path.exists() for path in paths.values())
    assert manifest.is_file()


def test_runtime_build_artifacts_are_optional(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    manifest = tmp_path / "opt/haloloom/base.json"

    prune_mod.prune(tmp_path, manifest, dry_run=False, runtime=False)

    assert paths["runtime_build"].exists()
