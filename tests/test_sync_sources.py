from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "sync_sources.py"
spec = importlib.util.spec_from_file_location("haloloom_sync_sources", MODULE_PATH)
assert spec and spec.loader
sync_sources = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sync_sources
spec.loader.exec_module(sync_sources)


def _manifest():
    return {
        "components": {
            "hyperloom": {
                "repository": "https://github.com/example/hyperloom",
                "commit": "a" * 40,
            },
            "magpie": {
                "repository": "https://github.com/example/magpie",
                "commit": "b" * 40,
            },
            "intellikit": {
                "repository": "https://github.com/example/intellikit",
                "commit": "d" * 40,
            },
            "tracelens": {
                "repository": "https://github.com/example/tracelens",
                "commit": "1" * 40,
            },
            "geak": {
                "repository": "https://github.com/example/geak",
                "commit": "c" * 40,
            },
            "inferencex": {
                "repository": "https://github.com/example/inferencex",
                "commit": "2" * 40,
            },
            "vllm": {
                "repository": "https://github.com/example/vllm",
                "commit": "e" * 40,
            },
            "lowbit_kernel_pack": {
                "repository": "https://github.com/example/lowbit",
                "commit": "f" * 40,
            },
        }
    }


def test_selected_components_defaults_to_friend_facing_sources() -> None:
    selected = sync_sources.selected_components(
        _manifest(), include_build_sources=False
    )
    assert [row.name for row in selected] == [
        "hyperloom",
        "magpie",
        "intellikit",
        "tracelens",
        "geak",
        "inferencex",
        "lowbit_kernel_pack",
    ]


def test_selected_components_can_include_build_sources_but_not_unpinned_rows() -> None:
    selected = sync_sources.selected_components(_manifest(), include_build_sources=True)
    assert [row.name for row in selected] == [
        "hyperloom",
        "magpie",
        "intellikit",
        "tracelens",
        "geak",
        "inferencex",
        "lowbit_kernel_pack",
        "vllm",
    ]
    assert all(len(row.commit) == 40 for row in selected)


def test_clone_command_is_detached_and_blob_filtered(tmp_path: Path) -> None:
    component = sync_sources.Component(
        "geak", "https://github.com/example/geak", "c" * 40
    )
    commands = sync_sources.clone_commands(component, tmp_path / "GEAK")
    assert commands[0][:4] == ["git", "clone", "--filter=blob:none", "--no-checkout"]
    assert commands[1][-2:] == ["--detach", "c" * 40]
