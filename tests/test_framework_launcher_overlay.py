"""Exercise the exact native overlay's vLLM block on real temporary files.

Isolate its AST block to avoid running a privileged full-image reconciler on
this host. Installed-image verification exercises the full entrypoint.
"""
import ast
import base64
import csv
import hashlib
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_source_current_overlay.py"
FILES = ("vllm/model_executor/models/qwen3_5.py", "vllm/entrypoints/launcher.py")


def record_values(path):
    return ["sha256=" + base64.urlsafe_b64encode(
        hashlib.sha256(path.read_bytes()).digest()).rstrip(b"=").decode(),
        str(path.stat().st_size)]


def prepare(tmp_path):
    repo, package = tmp_path / "source", tmp_path / "installed"
    rows = []
    for name in FILES:
        src, dst = repo / name, package / name
        src.parent.mkdir(parents=True, exist_ok=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("source " + name)
        dst.write_text("source " + name if "qwen3_5.py" in name else "old launcher")
        rows.append([name, *record_values(dst)])
    native = package / "vllm/native-control.so"
    native.write_bytes(b"unchanged test-only native sentinel")
    info = package / "vllm-test.dist-info"
    info.mkdir()
    record = info / "RECORD"
    with record.open("w", newline="") as f:
        csv.writer(f).writerows(rows)
    tree = ast.parse(SCRIPT.read_text())
    blocks: list[ast.stmt] = [n for n in tree.body if isinstance(n, ast.If)
                              and ast.unparse(n.test) == "v is not None"]
    assert len(blocks) == 1  # Fixture setup, deliberately outside pytest.raises.
    namespace = dict(
        allowed={"vllm": str(repo)},
        v=SimpleNamespace(locate_file=lambda name: package / name, _path=info),
        Path=Path, shutil=shutil, csv=csv, base64=base64, hashlib=hashlib,
    )
    code = compile(ast.Module(body=blocks, type_ignores=[]), str(SCRIPT), "exec")
    return repo, package, record, native, code, namespace


def test_native_overlay_installs_launcher_and_updates_record(tmp_path):
    repo, package, record, native, code, namespace = prepare(tmp_path)
    exec(code, dict(namespace, verify_only=False))
    assert native.read_bytes() == b"unchanged test-only native sentinel"
    with record.open(newline="") as f:
        rows = {r[0]: r[1:] for r in csv.reader(f)}
    for name in FILES:
        assert (package / name).read_bytes() == (repo / name).read_bytes()
        assert rows[name] == record_values(package / name)
    exec(code, dict(namespace, verify_only=True))


def test_native_overlay_verify_rejects_stale_launcher(tmp_path):
    _, _, _, _, code, namespace = prepare(tmp_path)
    with pytest.raises(AssertionError, match="launcher.py"):
        exec(code, dict(namespace, verify_only=True))
