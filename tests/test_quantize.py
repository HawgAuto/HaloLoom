from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "quantize.py"
spec = importlib.util.spec_from_file_location("haloloom_quantize", MODULE_PATH)
assert spec and spec.loader
quantize = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = quantize
spec.loader.exec_module(quantize)


def test_build_command_matches_original_quark_cli() -> None:
    command = quantize.build_command(
        provider="hermes",
        prompt="Quantize /workspace/model with W8A8",
        workspace="qwen-w8a8",
        model_id="gpt-test",
        extra=[],
    )
    assert command[:7] == [
        "docker",
        "compose",
        "run",
        "--rm",
        "-e",
        "HALOLOOM_PARENT_GPU_LOCK=1",
        "quark",
    ]
    assert command[-10:] == [
        "--provider",
        "hermes",
        "--prompt",
        "Quantize /workspace/model with W8A8",
        "--workspace",
        "/workspace/qwen-w8a8",
        "--interactive",
        "off",
        "--model-id",
        "gpt-test",
    ]


def test_workspace_is_single_relative_name() -> None:
    for bad in ("/tmp/job", "../job", "a/b", ""):
        try:
            quantize.build_command(
                provider="hermes", prompt="p", workspace=bad, model_id=None, extra=[]
            )
        except ValueError as error:
            assert "workspace" in str(error)
        else:
            raise AssertionError(bad)


def test_provider_is_explicit_and_bounded() -> None:
    try:
        quantize.build_command(
            provider="fallback", prompt="p", workspace="job", model_id=None, extra=[]
        )
    except ValueError as error:
        assert "provider" in str(error)
    else:
        raise AssertionError("unsupported provider accepted")


def test_provider_defaults_to_installer_selected_agent(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("HALOLOOM_AGENT_PROFILE=codex\n", encoding="utf-8")
    assert quantize.resolve_provider(None, env_file) == "codex"


def test_provider_must_match_installer_selected_agent(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("HALOLOOM_AGENT_PROFILE=hermes\n", encoding="utf-8")
    try:
        quantize.resolve_provider("codex", env_file)
    except ValueError as error:
        assert "rerun ./scripts/install.sh --agent codex" in str(error)
    else:
        raise AssertionError("mismatched provider accepted")
