from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "serve.py"
spec = importlib.util.spec_from_file_location("haloloom_serve", MODULE_PATH)
assert spec and spec.loader
serve = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = serve
spec.loader.exec_module(serve)


def test_vllm_command_uses_foreground_compose_service() -> None:
    command = serve.build_command("vllm", "Qwen/Qwen3-0.6B", [], max_model_len=4096)
    assert command[:6] == [
        "docker",
        "compose",
        "run",
        "--rm",
        "--service-ports",
        "vllm",
    ]
    assert command[-5:] == [
        "--model",
        "Qwen/Qwen3-0.6B",
        "--trust-remote-code",
        "--max-model-len",
        "4096",
    ]
    assert "--disable-log-requests" not in command


def test_sglang_command_pins_qualified_triton_route() -> None:
    command = serve.build_command("sglang", "Qwen/Qwen3-0.6B", [], max_model_len=4096)
    assert "--attention-backend" in command
    assert command[command.index("--attention-backend") + 1] == "triton"
    assert "--disable-cuda-graph" in command
    assert "--mem-fraction-static" in command
    assert command[command.index("--host") + 1] == "0.0.0.0"
    assert command[command.index("--port") + 1] == "8000"


def test_sglang_rejects_route_breaking_overrides() -> None:
    for extra in (["--attention-backend", "aiter"], ["--enable-cuda-graph"]):
        try:
            serve.build_command("sglang", "model", extra, max_model_len=4096)
        except ValueError as error:
            assert "qualified SGLang route" in str(error)
        else:
            raise AssertionError(extra)


def test_child_environment_removes_architecture_spoof() -> None:
    env = serve.child_environment(
        {"HSA_OVERRIDE_GFX_VERSION": "11.5.1", "HOME": "/home/u"}
    )
    assert "HSA_OVERRIDE_GFX_VERSION" not in env
    assert env["HOME"] == "/home/u"


def test_lowbit_requires_exact_model_revision() -> None:
    for revision in (None, "main", "abc123"):
        try:
            serve.build_command(
                "vllm",
                "model",
                ["--quantization", "gfx1151-w4a8"],
                max_model_len=2048,
                model_revision=revision,
            )
        except ValueError as error:
            assert "40-character model revision" in str(error)
        else:
            raise AssertionError(revision)


def test_lowbit_injects_framework_revision_and_bridge_environment() -> None:
    revision = "2fc06364715b967f1860aea9cf38778875588b17"
    for framework, variable in (
        ("vllm", "VLLM_GFX1151_LOWBIT_MODEL_REVISION"),
        ("sglang", "SGLANG_GFX1151_LOWBIT_MODEL_REVISION"),
    ):
        command = serve.build_command(
            framework,
            "model",
            ["--quantization=gfx1151-w4a8"],
            max_model_len=2048,
            model_revision=revision,
        )
        service_index = command.index(framework)
        prefix = command[:service_index]
        assert ["--env", "HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1"] == prefix[-4:-2]
        assert ["--env", f"{variable}={revision}"] == prefix[-2:]
        assert command[command.index("--revision") + 1] == revision


def test_cli_parses_launcher_options_before_framework_separator() -> None:
    revision = "2fc06364715b967f1860aea9cf38778875588b17"
    args = serve.parse_cli(
        [
            "vllm",
            "model",
            "--model-revision",
            revision,
            "--max-model-len",
            "2048",
            "--",
            "--quantization",
            "gfx1151-w4a8",
        ]
    )
    assert args.model_revision == revision
    assert args.max_model_len == 2048
    assert args.extra == ["--quantization", "gfx1151-w4a8"]
