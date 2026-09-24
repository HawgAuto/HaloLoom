"""V2 binds all HaloLoom Codex roles to one selected AMD-capable CLI."""

import os
from pathlib import Path
import subprocess


ENTRYPOINT = Path(__file__).resolve().parents[1] / "docker/ecosystem/workbench-entrypoint"


def test_workbench_rejects_split_cli_env_and_accepts_one_amd_runtime(tmp_path):
    upstream_cli = tmp_path / "codex-amd-upstream"
    upstream_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    upstream_cli.chmod(0o755)
    stale_cli = tmp_path / "codex-geak-old"
    stale_cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stale_cli.chmod(0o755)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = {**os.environ,
           "HALOLOOM_AGENT_PROFILE": "codex",
           "HALOLOOM_CODEX_BIN_IMAGE": str(upstream_cli),
           "GEAK_CODEX_BIN": str(upstream_cli),
           "INFERENCE_OPTIMIZER_CODEX_BIN": str(upstream_cli),
           "GEAK_PROFILE": "haloloom-v2-astra-upstream",
           "USER_DATA_PATH": str(workspace),
           "HYPERLOOM_RUNTIME_DIR": str(workspace / "runtime"),
           "KERNEL_AGENT_ENV": str(workspace / "runtime" / "kernel-agent.env.sh"),
           "CODEX_HOME": str(tmp_path / "no-auth"),
           "XDG_CACHE_HOME": str(workspace / "cache"),
           "VLLM_CACHE_ROOT": str(workspace / "vllm-cache"),
           "VLLM_CONFIG_ROOT": str(workspace / "vllm-config"),
           "TORCHINDUCTOR_CACHE_DIR": str(workspace / "inductor"),
           "TRITON_CACHE_DIR": str(workspace / "triton"),
           }
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "shell", "-lc",
         'printf "%s\\n%s\\n%s\\n" "$INFERENCE_OPTIMIZER_CODEX_BIN" "$GEAK_CODEX_BIN" "$GEAK_PROFILE"'],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(upstream_cli), str(upstream_cli), "haloloom-v2-astra-upstream"]
    env["GEAK_CODEX_BIN"] = str(stale_cli)
    rejected = subprocess.run(
        ["bash", str(ENTRYPOINT), "shell", "-lc", "true"],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert rejected.returncode != 0
    assert "forbids split Codex CLI selections" in rejected.stderr
    env["GEAK_CODEX_BIN"] = str(upstream_cli)
    env["INFERENCE_OPTIMIZER_CODEX_BIN"] = str(stale_cli)
    rejected = subprocess.run(
        ["bash", str(ENTRYPOINT), "shell", "-lc", "true"],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert rejected.returncode != 0
    assert "forbids split Codex CLI selections" in rejected.stderr
