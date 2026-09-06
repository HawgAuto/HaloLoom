from __future__ import annotations

import importlib.util
import json
import stat
import sys
import types
import urllib.request
from pathlib import Path

import pytest

VALIDATORS = Path(__file__).parents[1] / "qualification" / "validators"
MODULE_PATH = VALIDATORS / "run_rdna35_lowbit_framework_route_v7.py"
sys.path.insert(0, str(VALIDATORS))
spec = importlib.util.spec_from_file_location("framework_route_v7", MODULE_PATH)
assert spec and spec.loader
route = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = route
spec.loader.exec_module(route)


def test_private_sglang_admin_config_is_native_and_ephemeral(tmp_path: Path) -> None:
    secret = "selected-region-admin-secret"

    with route._private_sglang_admin_config(secret, directory=tmp_path) as config:
        assert config.suffix == ".yaml"
        assert stat.S_IMODE(config.stat().st_mode) == 0o600
        assert json.loads(config.read_text(encoding="utf-8")) == {
            "admin-api-key": secret
        }
        assert secret not in str(config)

    assert not config.exists()


def test_sglang_selected_region_command_uses_config_without_secret(tmp_path: Path) -> None:
    config = tmp_path / "private.yaml"
    secret = "must-not-appear-in-argv"
    config.write_text(json.dumps({"admin-api-key": secret}), encoding="utf-8")

    command = route._server_command(
        framework="sglang",
        model=tmp_path / "model",
        served_model_name="model",
        quantization="modelopt_fp8",
        port=30000,
        profile_selected_regions=True,
        admin_config=config,
    )

    config_index = command.index("--config")
    assert command[config_index + 1] == str(config)
    assert "--config" in command
    assert secret not in " ".join(command)
    assert "--admin-api-key" not in command


def test_sglang_profiler_lane_preserves_safe_weight_loading(tmp_path: Path) -> None:
    command = route._server_command(
        framework="sglang", model=tmp_path / "model", served_model_name="model",
        quantization="gfx1151-w8a8", port=30000,
        profile_selected_regions=True, admin_config=tmp_path / "private.yaml",
    )
    assert "--weight-loader-disable-mmap" in command
    position = command.index("--model-loader-extra-config")
    assert json.loads(command[position + 1]) == {"enable_multithread_load": False}


def test_vllm_command_is_unchanged_by_selected_region_admin_auth(tmp_path: Path) -> None:
    baseline = route._server_command(
        framework="vllm",
        model=tmp_path / "model",
        served_model_name="model",
        quantization="compressed-tensors",
        port=30000,
        profile_selected_regions=True,
    )
    assert "--config" not in baseline
    assert "--admin-api-key" not in baseline


def test_profile_control_sends_bearer_without_returning_secret(monkeypatch) -> None:
    captured: dict[str, object] = {}
    secret = "selected-region-admin-secret"

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b"Finalized profiler worker.\n"

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(route.urllib.request, "urlopen", fake_urlopen)
    receipt = route._post_profile_control(
        "http://127.0.0.1:30000/finalize_profile_worker",
        admin_token=secret,
    )

    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.get_header("Authorization") == f"Bearer {secret}"
    assert secret not in json.dumps(receipt, sort_keys=True)


def test_profile_control_omits_authorization_without_admin_token(monkeypatch) -> None:
    captured: dict[str, urllib.request.Request] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b"Start profiling.\n"

    def fake_urlopen(request: urllib.request.Request, timeout: float):
        captured["request"] = request
        return Response()

    monkeypatch.setattr(route.urllib.request, "urlopen", fake_urlopen)
    route._post_profile_control("http://127.0.0.1:30000/start_profile")
    assert captured["request"].get_header("Authorization") is None


def test_admin_config_rejects_empty_token(tmp_path: Path) -> None:
    with pytest.raises(route.FrameworkRouteError, match="admin token"):
        with route._private_sglang_admin_config("", directory=tmp_path):
            pass
    assert list(tmp_path.iterdir()) == []


def test_private_admin_config_is_removed_after_body_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="body failed"):
        with route._private_sglang_admin_config("secret", directory=tmp_path):
            raise RuntimeError("body failed")
    assert list(tmp_path.iterdir()) == []


def test_sglang_config_repr_gate_rejects_secret_disclosure(
    monkeypatch, tmp_path: Path
) -> None:
    secret = "repr-disclosure-sentinel"

    class UnsafeServerArgs:
        def __init__(self, **values):
            self.values = values

        def resolved_dict(self):
            return self.values

    package = types.ModuleType("sglang")
    srt = types.ModuleType("sglang.srt")
    module = types.ModuleType("sglang.srt.server_args")
    setattr(module, "ServerArgs", UnsafeServerArgs)
    monkeypatch.setitem(sys.modules, "sglang", package)
    monkeypatch.setitem(sys.modules, "sglang.srt", srt)
    monkeypatch.setitem(sys.modules, "sglang.srt.server_args", module)

    with pytest.raises(route.FrameworkRouteError) as caught:
        route._verify_sglang_admin_config_redaction(secret, tmp_path / "model")
    assert secret not in str(caught.value)


@pytest.mark.parametrize("preserve_internal", [True, False])
def test_redaction_gate_uses_public_view_and_preserves_internal_auth(
    monkeypatch, tmp_path: Path, preserve_internal: bool
) -> None:
    secret = "internal-auth-sentinel"

    class ServerArgs:
        def __init__(self, **values):
            self.values = values

        def public_dict(self):
            return {**self.values, "admin_api_key": "[REDACTED]"}

        def resolved_dict(self):
            return self.values if preserve_internal else self.public_dict()

    module = types.ModuleType("sglang.srt.server_args")
    setattr(module, "ServerArgs", ServerArgs)
    monkeypatch.setitem(sys.modules, "sglang", types.ModuleType("sglang"))
    monkeypatch.setitem(sys.modules, "sglang.srt", types.ModuleType("sglang.srt"))
    monkeypatch.setitem(sys.modules, "sglang.srt.server_args", module)
    if preserve_internal:
        route._verify_sglang_admin_config_redaction(secret, tmp_path / "model")
    else:
        with pytest.raises(route.FrameworkRouteError, match="internal"):
            route._verify_sglang_admin_config_redaction(secret, tmp_path / "model")
