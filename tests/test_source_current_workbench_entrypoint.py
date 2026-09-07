"""Regression for the workbench included in the source-bound overlay.

Archive inclusion keeps the existing deny-by-default build context unchanged.
Exact installed bytes and selected CLI execution are verified on the real image.
"""
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "dist/source-current/workbench-entrypoint"
DESTINATION = "/opt/haloloom/workbench-entrypoint"


def test_shared_overlay_copies_current_executable_entrypoint():
    shared = (ROOT / "docker/source-current/Dockerfile").read_text().split(
        "FROM source-current AS vllm", 1
    )[0]
    copies = [shlex.split(line) for line in shared.splitlines()
              if line.startswith("COPY ")]
    selected = [parts for parts in copies
                if parts[-2:] == [SOURCE, DESTINATION]]
    assert len(selected) == 1, "source-current overlay leaves stale base entrypoint"
    assert "--chmod=0755" in selected[0], "entrypoint must be executable"


def test_selected_cli_export_remains_in_archived_source():
    entrypoint = (ROOT / "docker/ecosystem/workbench-entrypoint").read_text()
    codex = entrypoint.split("  codex)\n", 1)[1].split("    ;;", 1)[0]
    assert 'export INFERENCE_OPTIMIZER_CODEX_BIN="${INFERENCE_OPTIMIZER_CODEX_BIN:-$agent_bin}"' in codex
    assert 'export GEAK_CODEX_BIN="$agent_bin"' in codex
