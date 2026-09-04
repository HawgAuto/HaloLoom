from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "runtime_identity.py"
spec = importlib.util.spec_from_file_location("haloloom_runtime_identity", MODULE_PATH)
assert spec and spec.loader
runtime_identity = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime_identity
spec.loader.exec_module(runtime_identity)


def test_tree_identity_is_deterministic_and_content_sensitive(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "a.py").write_text("x = 1\n", encoding="utf-8")
    (package / "data.bin").write_bytes(b"abc")

    first = runtime_identity.tree_identity(package)
    second = runtime_identity.tree_identity(package)
    assert first == second
    assert first["file_count"] == 2

    (package / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert runtime_identity.tree_identity(package)["sha256"] != first["sha256"]


def test_tree_identity_ignores_python_cache(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "a.py").write_text("x = 1\n", encoding="utf-8")
    before = runtime_identity.tree_identity(package)
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "a.pyc").write_bytes(b"unstable")
    assert runtime_identity.tree_identity(package) == before
