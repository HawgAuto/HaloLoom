"""Only an exact declared earlier overlay may advance to a later source ref."""
import ast
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_source_current_overlay.py"


def setup_case(tmp_path):
    origin, work = tmp_path / "origin", tmp_path / "working"
    origin.mkdir()
    def run(repo, *args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
    run(origin, "init", "-q")
    run(origin, "config", "user.name", "CPU Fixture")
    run(origin, "config", "user.email", "fixture@example.invalid")
    (origin / "model.py").write_text("model base\n")
    (origin / "launcher.py").write_text("launcher base\n")
    def commit(label):
        run(origin, "add", "model.py", "launcher.py")
        run(origin, "-c", "commit.gpgsign=false", "commit", "-qm", label)
        return run(origin, "rev-parse", "HEAD"), run(origin, "rev-parse", "HEAD^{tree}")
    base, _ = commit("base")
    (origin / "model.py").write_text("verified model overlay\n")
    predecessor, predecessor_tree = commit("verified overlay")
    (origin / "launcher.py").write_text("signal-owner repair\n")
    target, target_tree = commit("successor")
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(origin), str(work)], check=True)
    run(work, "checkout", "-q", "--detach", base)
    (work / "model.py").write_text("verified model overlay\n")
    component = dict(path=str(work), base=base, ref=target, tree=target_tree,
                     transport="origin", overlay_predecessor={
                         "ref": predecessor, "tree": predecessor_tree})
    tree = ast.parse(SCRIPT.read_text())
    body: list[ast.stmt] = [n for n in tree.body if
        isinstance(n, ast.FunctionDef) and n.name == "git" or
        isinstance(n, ast.For) and isinstance(n.target, ast.Tuple) and
        [getattr(x, "id", None) for x in n.target.elts] == ["name", "c"]]
    assert len(body) == 2
    namespace = dict(Path=Path, os=os, subprocess=subprocess, root=tmp_path,
                     allowed={"vllm": str(work)}, m={"components": {"vllm": component}},
                     verify_only=False)
    code = compile(ast.Module(body=body, type_ignores=[]), str(SCRIPT), "exec")
    return origin, work, component, code, namespace, run


def test_exact_overlay_predecessor_can_advance(tmp_path):
    origin, work, component, code, namespace, run = setup_case(tmp_path)
    exec(code, namespace)
    assert run(work, "rev-parse", "HEAD") == component["ref"]
    assert not run(work, "status", "--porcelain")
    assert (work / "model.py").read_bytes() == (origin / "model.py").read_bytes()
    assert (work / "launcher.py").read_bytes() == (origin / "launcher.py").read_bytes()


def test_unknown_dirty_source_is_never_discarded(tmp_path):
    _, work, component, code, namespace, run = setup_case(tmp_path)
    bad = b"unexpected local edit\n"
    (work / "launcher.py").write_bytes(bad)
    with pytest.raises(AssertionError):
        exec(code, namespace)
    assert run(work, "rev-parse", "HEAD") == component["base"]
    assert (work / "launcher.py").read_bytes() == bad


def test_incorrect_predecessor_tree_is_rejected(tmp_path):
    _, work, component, code, namespace, run = setup_case(tmp_path)
    predecessor = component["overlay_predecessor"]
    assert isinstance(predecessor, dict)
    predecessor["tree"] = "0" * 40
    with pytest.raises(AssertionError):
        exec(code, namespace)
    assert run(work, "rev-parse", "HEAD") == component["base"]
