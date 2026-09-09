"""Offline source/package reconciliation in a NEW image only."""
import base64
import csv
import hashlib
import importlib.metadata as md
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

root = Path('/opt/haloloom/source-current')
m = json.loads((root / 'manifest.json').read_text())
verify_only = '--verify-only' in sys.argv
allowed = {
    'hyperloom': '/opt/haloloom/components/Hyperloom',
    'geak': '/opt/haloloom/components/GEAK',
    'intellikit': '/opt/haloloom/components/IntelliKit',
    'vllm': '/opt/haloloom/framework-source/vllm',
    'sglang': '/opt/haloloom/framework-source/sglang',
}

def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def dist(name):
    try:
        return md.distribution(name)
    except md.PackageNotFoundError:
        return None

def native_map():
    values = {}
    for name, package in [('vllm', 'vllm'), ('sglang-kernel', 'sgl_kernel')]:
        d = dist(name)
        if d is not None:
            for p in Path(str(d.locate_file(package))).rglob('*.so'):
                values[str(p)] = sha(p)
    return values

def git(c, *args):
    p = Path(c['path'])
    owner = p.stat()
    return subprocess.check_output(
        ['git', '-C', str(p), *args], text=True,
        user=owner.st_uid if os.getuid() == 0 else None,
        group=owner.st_gid if os.getuid() == 0 else None,
        timeout=120,
    ).strip()

assert not Path('/dev/kfd').exists(), 'build/verification requires no GPU'
for path, digest in m['files'].items():
    p = root / path
    assert p.resolve().is_relative_to(root.resolve())
    assert sha(p) == digest, path
native_before = native_map()
for name, c in m['components'].items():
    assert c['path'] == allowed[name]
    current = git(c, 'rev-parse', 'HEAD')
    assert current in (c['base'], c['ref']), (name, current)
    if not verify_only and current != c['ref']:
        dirty = git(c, 'status', '--porcelain', '--untracked-files=no')
        if name != 'vllm':
            assert not dirty, (name, dirty)
        transport = str(root / c['transport'])
        git(c, 'fetch', '--no-tags', '--update-shallow', transport, 'HEAD')
        assert git(c, 'rev-parse', 'FETCH_HEAD') == c['ref']
        if dirty:
            # A verified Python overlay can precede this source revision. Bind
            # the complete older tree before moving HEAD/index; never discard
            # arbitrary edits or force a checkout over untracked source files.
            assert name == 'vllm'
            reconciled_ref = c['ref']
            if git(c, 'diff', reconciled_ref, '--name-only'):
                predecessor = c.get('overlay_predecessor', {})
                assert isinstance(predecessor, dict), dirty
                previous = predecessor.get('ref', '')
                previous_tree = predecessor.get('tree', '')
                assert all(isinstance(value, str) and len(value) == 40
                           and all(ch in '0123456789abcdef' for ch in value)
                           for value in (previous, previous_tree)), dirty
                assert git(c, 'rev-parse', previous + '^{tree}') == previous_tree
                git(c, 'merge-base', '--is-ancestor', previous, c['ref'])
                reconciled_ref = previous
            assert not git(c, 'diff', reconciled_ref, '--name-only'), dirty
            git(c, 'reset', '--mixed', reconciled_ref)
            if reconciled_ref != c['ref']:
                git(c, 'checkout', '--detach', c['ref'])
        else:
            git(c, 'checkout', '--detach', c['ref'])
    assert git(c, 'rev-parse', 'HEAD') == c['ref'], name
    assert git(c, 'rev-parse', 'HEAD^{tree}') == c['tree'], name
    assert not git(c, 'diff', 'HEAD', '--name-only'), name

ref = json.loads((root / 'component-source-reference.json').read_text())
hyper_source = Path(allowed['hyperloom'])
assert ref['ref'] == m['components']['hyperloom']['ref']
assert all((hyper_source / p).is_file() and sha(hyper_source / p) == h
           for p, h in ref['expected'].items())

wheel_counts = {}
for name, distribution in [('hyperloom', 'hyperloom-inference-optimizer'), ('sglang', 'sglang'), ('geak','geak'), ('intellikit', 'metrix')]:
    # Historical archives have no IntelliKit update; keep them verifiable.
    if name == 'intellikit' and name not in m['components']:
        continue
    c = m['components'][name]
    wheel = root / c['wheel']
    assert sha(wheel) == c['wheel_sha256']
    d = dist(distribution)
    if d is None:
        assert name == 'sglang'
        continue
    with zipfile.ZipFile(wheel) as z:
        names = [n for n in z.namelist() if n.endswith('.py')]
        assert not any('.data/' in n for n in names)
        if name == 'intellikit':
            assert all(n.startswith('metrix/') and '..' not in Path(n).parts
                       for n in names), names
        mismatch = [n for n in names if not Path(str(d.locate_file(n))).is_file()
                    or Path(str(d.locate_file(n))).read_bytes() != z.read(n)]
        if mismatch and not verify_only:
            # Only the named pure-Python control/profiling packages may be
            # reinstalled. Never upgrade a serving backend or native library.
            assert name in ('hyperloom','geak','intellikit'), mismatch
            assert not any(n.endswith('.so') for n in z.namelist())
            subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps',
                            '--no-index', '--force-reinstall', str(wheel)], check=True)
            d = md.distribution(distribution)
        assert all(Path(str(d.locate_file(n))).read_bytes() == z.read(n) for n in names)
        wheel_counts[name] = len(names)

v = dist('vllm')
if v is not None:
    record = Path(getattr(v, '_path')) / 'RECORD'
    with record.open(newline='') as f:
        rows = list(csv.reader(f))
    for relative in ('vllm/model_executor/models/qwen3_5.py',
                     'vllm/entrypoints/launcher.py'):
        source = Path(allowed['vllm']) / relative
        destination = Path(str(v.locate_file(relative)))
        matches = [row for row in rows if row and row[0] == relative]
        assert len(matches) == 1 and len(matches[0]) == 3, relative
        if not verify_only:
            shutil.copyfile(source, destination)
        assert source.read_bytes() == destination.read_bytes(), relative
        expected = ['sha256=' + base64.urlsafe_b64encode(
            hashlib.sha256(destination.read_bytes()).digest()
        ).rstrip(b'=').decode(), str(destination.stat().st_size)]
        if not verify_only:
            matches[0][1:] = expected
        assert matches[0][1:] == expected, relative
    if not verify_only:
        with record.open('w', newline='') as f:
            csv.writer(f).writerows(rows)

subprocess.run([sys.executable,str(root/'apply-geak-integration.py')]+(['--verify-only'] if verify_only else []),check=True)
subprocess.run([sys.executable,str(root/'apply-quark-dense-qwen35.py')]+(['--verify-only'] if verify_only else []),check=True)
assert native_before == native_map()
result = {
    'status': 'PASS_SOURCE_CURRENT_CPU_ONLY',
    'refs': {n: c['ref'] for n, c in m['components'].items()},
    'component_files_verified': len(ref['expected']),
    'component_python_files_verified': sum(p.endswith('.py') for p in ref['expected']),
    'installed_wheel_python_files': wheel_counts,
    'native_files': native_before,
    'no_gpu': True,
    'promotion_authority': False,
}
if verify_only:
    old = json.loads((root / 'build-receipt.json').read_text())
    assert result == old
else:
    (root / 'build-receipt.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
