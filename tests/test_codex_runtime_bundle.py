"""Codex runtime closure regressions; fixtures contain no real credentials."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "scripts" / "detect_agent_plugins.py"
SPEC = importlib.util.spec_from_file_location("plugins_codex_bundle_regression", PATH)
assert SPEC and SPEC.loader
plugins = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = plugins
SPEC.loader.exec_module(plugins)


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def bundle(path: Path) -> Path:
    binary = executable(path / "bin" / "codex")
    executable(path / "bin" / "codex-code-mode-host")
    (path / "codex-resources").mkdir()
    (path / "codex-path").mkdir()
    (path / "codex-package.json").write_text(
        json.dumps(
            {
                "layoutVersion": 1,
                "version": "0.153.4",
                "target": "x86_64-unknown-linux-musl",
                "variant": "codex",
                "entrypoint": "bin/codex",
                "resourcesDir": "codex-resources",
                "pathDir": "codex-path",
            }
        ),
        encoding="utf-8",
    )
    return binary


def detect(path_bin: Path, tmp_path: Path):
    return plugins.detect_plugins(
        path_env=str(path_bin),
        home=tmp_path / "home",
        state_dir=tmp_path / "state",
        requested="codex",
    )["env"]


def test_native_bundle_mount_covers_helpers_and_resources(tmp_path: Path) -> None:
    root = tmp_path / "vendor" / "x86_64-unknown-linux-musl"
    binary = bundle(root)
    path_bin = tmp_path / "path-bin"
    path_bin.mkdir()
    (path_bin / "codex").symlink_to(binary)
    env = detect(path_bin, tmp_path)
    assert Path(env["HALOLOOM_CODEX_ROOT_HOST"]) == root
    assert Path(env["HALOLOOM_CODEX_BIN_HOST"]) == binary


@pytest.mark.parametrize("nested", [False, True])
def test_npm_plugin_selects_exact_native_bundle_not_js_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    nested: bool,
) -> None:
    # The real npm launcher uses platform+architecture-specific optional packages.
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    modules = tmp_path / "prefix" / "node_modules"
    wrapper = modules / "@openai" / "codex"
    js = executable(wrapper / "bin" / "codex.js")
    (wrapper / "package.json").write_text(
        json.dumps(
            {
                "name": "@openai/codex",
                "version": "0.153.4",
                "optionalDependencies": {
                    "@openai/codex-linux-x64": "npm:@openai/codex@0.153.4-linux-x64"
                },
            }
        ),
        encoding="utf-8",
    )
    dependency_root = wrapper / "node_modules" if nested else modules
    root = (
        dependency_root
        / "@openai"
        / "codex-linux-x64"
        / "vendor"
        / "x86_64-unknown-linux-musl"
    )
    binary = bundle(root)
    (root.parents[1] / "package.json").write_text(
        '{"name":"@openai/codex","version":"0.153.4-linux-x64"}', encoding="utf-8"
    )
    path_bin = tmp_path / "path-bin"
    path_bin.mkdir()
    (path_bin / "codex").symlink_to(js)
    env = detect(path_bin, tmp_path)
    assert Path(env["HALOLOOM_CODEX_ROOT_HOST"]) == root
    assert Path(env["HALOLOOM_CODEX_BIN_HOST"]) == binary


def test_npm_plugin_rejects_js_wrapper_when_native_bundle_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    modules = tmp_path / "prefix" / "node_modules"
    wrapper = modules / "@openai" / "codex"
    js = executable(wrapper / "bin" / "codex.js")
    (wrapper / "package.json").write_text(
        json.dumps(
            {
                "name": "@openai/codex",
                "version": "0.153.4",
                "optionalDependencies": {
                    "@openai/codex-linux-x64": "npm:@openai/codex@0.153.4-linux-x64"
                },
            }
        ),
        encoding="utf-8",
    )
    path_bin = tmp_path / "path-bin"
    path_bin.mkdir()
    (path_bin / "codex").symlink_to(js)
    with pytest.raises(RuntimeError, match="native Codex bundle"):
        detect(path_bin, tmp_path)


def test_bundle_requires_code_mode_helper(tmp_path: Path) -> None:
    root = tmp_path / "vendor" / "x86_64-unknown-linux-musl"
    binary = bundle(root)
    (root / "bin" / "codex-code-mode-host").unlink()
    with pytest.raises(RuntimeError, match="codex-code-mode-host"):
        plugins._codex_root(binary)


def test_bundle_entrypoint_cannot_escape_runtime_root(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    binary = bundle(root)
    metadata = root / "codex-package.json"
    data = json.loads(metadata.read_text())
    data["entrypoint"] = "../../outside/codex"
    metadata.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="(?i)(codex|entrypoint|bundle)"):
        plugins._codex_root(binary)


def test_both_entrypoints_export_explicit_sdk_executable() -> None:
    repo = Path(__file__).parents[1]
    for relative in [
        "docker/ecosystem/workbench-entrypoint",
        "docker/quark/plugin-entrypoint",
    ]:
        content = (repo / relative).read_text()
        assert (
            'export INFERENCE_OPTIMIZER_CODEX_BIN="${INFERENCE_OPTIMIZER_CODEX_BIN:-$agent_bin}"'
            in content
        )


def test_quark_entrypoint_updates_all_oauth_homes_after_private_copy() -> None:
    repo = Path(__file__).parents[1]
    content = (repo / "docker/quark/plugin-entrypoint").read_text()
    native = content.index("native_home=$(mktemp -d /tmp/haloloom-quark-codex-home")
    tail = content[native:]
    exports = [
        'export CODEX_HOME="$native_home"',
        'export HYPERLOOM_CODEX_HOME="$CODEX_HOME"',
        'export INFERENCE_OPTIMIZER_CODEX_HOME="$native_home"',
        'export GEAK_CODEX_HOME="$native_home"',
    ]
    positions = [tail.index(line) for line in exports]
    # Preserve the original alias contract: CODEX_HOME must point at the
    # private copy before the Hyperloom alias is expanded.
    assert positions == sorted(positions)
    assert tail.index('install -m 0600 "$CODEX_HOME/auth.json"') < positions[0]


def test_codex_standalone_binary_cannot_mount_entire_home(tmp_path: Path) -> None:
    home = tmp_path / "operator"
    executable(home / "codex")
    with pytest.raises(RuntimeError, match="dedicated installation directory"):
        plugins.detect_plugins(
            home=home,
            state_dir=tmp_path / "state",
            requested="codex",
            path_env=str(home),
        )


def test_codex_standalone_binary_cannot_mount_home_parent(tmp_path: Path) -> None:
    home = tmp_path / "operator"
    executable(tmp_path / "codex")
    with pytest.raises(RuntimeError, match="dedicated installation directory"):
        plugins.detect_plugins(
            home=home,
            state_dir=tmp_path / "state",
            requested="codex",
            path_env=str(tmp_path),
        )
