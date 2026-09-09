"""Metrix joins the protected offline overlay without widening backend writes.

Exercise the real wheel block on fixture bytes, mocking only the pip boundary.
The full installed reconciler is separately exercised in a no-device image.
"""
import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import sys
import zipfile

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/apply_source_current_overlay.py'


def prepare(tmp_path, *, verify_only=False, include_metrix=True, extra=None):
    root, site = tmp_path / 'payload', tmp_path / 'site'
    root.mkdir()
    site.mkdir()
    components = {}
    for name, package in [('hyperloom', 'hyperloom'), ('sglang', 'sglang'),
                          ('geak', 'geak'), ('intellikit', 'metrix')]:
        if name == 'intellikit' and not include_metrix:
            continue
        member = package + '/fixture.py'
        payload_bytes = b'new fixture\n' if name == 'intellikit' else b'unchanged fixture\n'
        wheel = root / (package + '.whl')
        with zipfile.ZipFile(wheel, 'w') as z:
            z.writestr(member, payload_bytes)
            if name == 'intellikit' and extra:
                z.writestr(*extra)
        target = site / member
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'old fixture\n' if name == 'intellikit' else payload_bytes)
        components[name] = dict(wheel=wheel.name,
                               wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest())
    native = site / 'unchanged-native.so'
    native.write_bytes(b'test-only immutable native sentinel')
    calls = []
    distribution = SimpleNamespace(locate_file=lambda n: site / n)
    def install(argv, *, check):
        assert check and argv[:3] == [sys.executable, '-m', 'pip']
        assert '--no-deps' in argv and '--no-index' in argv
        calls.append(argv)
        with zipfile.ZipFile(argv[-1]) as z:
            for n in z.namelist():
                dst = site / n
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(z.read(n))
    tree = ast.parse(SCRIPT.read_text())
    body: list[ast.stmt] = [n for n in tree.body if
        isinstance(n, ast.FunctionDef) and n.name == 'sha' or
        isinstance(n, ast.For) and isinstance(n.target, ast.Tuple) and
        [getattr(x, 'id', None) for x in n.target.elts] == ['name', 'distribution']]
    assert len(body) == 2
    ns: dict[str, Any] = dict(root=root, m={'components': components}, Path=Path, hashlib=hashlib,
              zipfile=zipfile, sys=sys, dist=lambda _: distribution,
              md=SimpleNamespace(distribution=lambda _: distribution),
              subprocess=SimpleNamespace(run=install), wheel_counts={},
              verify_only=verify_only)
    return compile(ast.Module(body=body, type_ignores=[]), str(SCRIPT), 'exec'), ns, site, native, calls


def test_intellikit_has_one_canonical_source_root():
    tree = ast.parse(SCRIPT.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'allowed' for t in n.targets))
    allowed = ast.literal_eval(node.value)
    assert allowed['intellikit'] == '/opt/haloloom/components/IntelliKit'


def test_metrix_overlay_materializes_then_verifies(tmp_path):
    code, ns, site, native, calls = prepare(tmp_path)
    exec(code, ns)
    assert len(calls) == 1
    assert (site / 'metrix/fixture.py').read_bytes() == b'new fixture\n'
    assert ns['wheel_counts']['intellikit'] == 1
    assert native.read_bytes() == b'test-only immutable native sentinel'
    ns['verify_only'] = True
    exec(code, ns)
    assert len(calls) == 1


def test_verify_does_not_repair_stale_metrix(tmp_path):
    code, ns, site, _, calls = prepare(tmp_path, verify_only=True)
    with pytest.raises(AssertionError):
        exec(code, ns)
    assert not calls
    assert (site / 'metrix/fixture.py').read_bytes() == b'old fixture\n'


@pytest.mark.parametrize('extra', [('metrix/unsafe.so', b'not native code'),
                                  ('vllm/foreign.py', b'not a serving overlay'),
                                  ('metrix/../../foreign.py', b'not a package path')])
def test_metrix_wheel_cannot_widen_its_write_scope(tmp_path, extra):
    code, ns, site, _, calls = prepare(tmp_path, extra=extra)
    with pytest.raises(AssertionError):
        exec(code, ns)
    assert not calls
    assert (site / 'metrix/fixture.py').read_bytes() == b'old fixture\n'


def test_legacy_manifest_remains_usable(tmp_path):
    code, ns, _, _, calls = prepare(tmp_path, include_metrix=False)
    exec(code, ns)
    assert not calls
    assert 'intellikit' not in ns['wheel_counts']
