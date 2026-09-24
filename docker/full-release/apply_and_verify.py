#!/usr/bin/env python3
"""Install and verify the complete hash-bound release in a new image only."""
from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path('/opt/haloloom/source-current')
TARGETS = {
    'Hyperloom': Path('/opt/haloloom/components/Hyperloom'),
    'GEAK': Path('/opt/haloloom/components/GEAK'),
    'TraceLens': Path('/opt/haloloom/components/TraceLens'),
    'Quark': Path('/opt/haloloom/components/Quark'),
    'vllm': Path('/opt/haloloom/framework-source/vllm'),
}
DISTRIBUTIONS = {'Hyperloom': 'hyperloom-inference-optimizer', 'GEAK': 'geak', 'TraceLens': 'TraceLens', 'Quark': 'amd-quark', 'vllm': 'vllm'}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(argv: list[str], **kwargs) -> str:
    kwargs.setdefault('env', {**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    return subprocess.check_output(argv, text=True, **kwargs).strip()


def checked_relative(root: Path, rel: str) -> Path:
    path = root / rel
    if Path(rel).is_absolute() or '..' in Path(rel).parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Unsafe relative path: {rel}')
    return path


def verify_tree(root: Path, spec: dict) -> None:
    assert run(['git', '-c', f'safe.directory={root}', '-C', str(root), 'rev-parse', 'HEAD']) == spec['ref']
    assert run(['git', '-c', f'safe.directory={root}', '-C', str(root), 'rev-parse', 'HEAD^{tree}']) == spec['tree']
    assert not run(['git', '-c', f'safe.directory={root}', '-C', str(root), 'diff', 'HEAD', '--name-only'])
    for rel, expected in spec['files'].items():
        assert digest(checked_relative(root, rel)) == expected, (root, rel)


def wheel_probe(executable: str, wheel: Path, distribution: str, *, install: bool) -> dict:
    code = r'''import hashlib,importlib.metadata as md,json,os,subprocess,sys,zipfile
from pathlib import Path
wheel,distribution,install=sys.argv[1:]
try:d=md.distribution(distribution)
except md.PackageNotFoundError:print(json.dumps({'installed':False}));raise SystemExit(0)
if install=='1':
 subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-deps','--force-reinstall',wheel],check=True,stdout=sys.stderr)
 d=md.distribution(distribution)
with zipfile.ZipFile(wheel) as z:
 names=[n for n in z.namelist() if n.endswith(('.py','.so')) and '.data/' not in n]
 bad=[n for n in names if not Path(d.locate_file(n)).is_file() or hashlib.sha256(Path(d.locate_file(n)).read_bytes()).digest()!=hashlib.sha256(z.read(n)).digest()]
 assert not bad,bad
 if install=='1':
  site=Path(d.locate_file('')).resolve()
  for name in names:
   path=Path(d.locate_file(name)).resolve()
   assert path.is_relative_to(site)
   os.chown(path,1000,1000)
   parent=path.parent
   while parent!=site:
    os.chown(parent,1000,1000)
    parent=parent.parent
 print(json.dumps({'installed':True,'version':d.version,'prefix':sys.prefix,'members_verified':len(names)}))
'''
    return json.loads(run([executable, '-B', '-c', code, str(wheel), distribution, '1' if install else '0']))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify-only', action='store_true')
    p.add_argument('--variant', choices=['vllm', 'sglang', 'quark'], required=True)
    args = p.parse_args()
    assert sys.prefix == '/opt/venv' and ROOT.is_dir(), 'qualified image interpreter and packet required'
    if not args.verify_only:
        assert os.geteuid() == 0, 'image installation requires root'
        assert not Path('/dev/kfd').exists() and not list(Path('/dev/dri').glob('renderD*')) and not list(Path('/dev').glob('nvidia[0-9]*')), 'no-device build required'
    m = json.loads((ROOT / 'manifest.json').read_text())
    assert m['schema_version'] == 4 and m['release'] == 'v0.1.4'
    assert set(m['components']) == set(TARGETS)
    for rel, expected in m['payload_files'].items():
        assert digest(checked_relative(ROOT, rel)) == expected, rel
    entrypoint = Path('/opt/haloloom/workbench-entrypoint')
    if not args.verify_only:
        shutil.copyfile(ROOT/'workbench-entrypoint', entrypoint)
        entrypoint.chmod(0o755)
    assert digest(entrypoint) == digest(ROOT/'workbench-entrypoint')
    assert os.access(entrypoint, os.X_OK)
    for name, spec in m['components'].items():
        source, destination = ROOT / 'sources' / name, TARGETS[name]
        verify_tree(source, spec)
        if not args.verify_only:
            # Preserve only installed third-party Node dependencies, never old source.
            nodes = destination / 'node_modules'
            retained = ROOT / 'retained-geak-node-modules'
            if name == 'GEAK' and nodes.exists():
                assert not retained.exists()
                shutil.move(str(nodes), retained)
            if destination.is_symlink():
                destination.unlink()
            elif destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(source, destination, symlinks=True)
            if name == 'GEAK' and retained.exists():
                shutil.move(str(retained), destination / 'node_modules')
            shutil.chown(destination, user=1000, group=1000)
            subprocess.run(['chown', '-R', '1000:1000', str(destination)], check=True)
        verify_tree(destination, spec)
    if not args.verify_only:
        for alias in [Path('/opt/quark-runtime-src'), Path('/opt/quark-source')]:
            if alias.is_symlink():
                alias.unlink()
            elif alias.exists():
                shutil.rmtree(alias)
            alias.symlink_to(TARGETS['Quark'])
    envs = ['/opt/venv/bin/python', '/opt/haloloom-agent/bin/python', '/opt/quark-venv/bin/python']
    result = {'source_refs': {n: s['ref'] for n, s in m['components'].items()}, 'variant': args.variant, 'environments': {}}
    for executable in envs:
        if not Path(executable).exists():
            continue
        records = {}
        for name, spec in m['components'].items():
            if name == 'vllm' and args.variant == 'sglang':
                continue
            records[name] = wheel_probe(executable, ROOT / 'wheels' / spec['wheel'], DISTRIBUTIONS[name], install=not args.verify_only)
            if records[name]['installed']:
                assert records[name]['version'] == spec['version'], (executable, name, records[name])
        result['environments'][executable] = records
    assert result['environments']['/opt/venv/bin/python']['Hyperloom']['installed']
    for name in ['GEAK', 'TraceLens']:
        assert result['environments']['/opt/venv/bin/python'][name]['installed']
    if args.variant in {'vllm', 'quark'}:
        assert result['environments']['/opt/venv/bin/python']['vllm']['installed']
    assert any(e.get('Quark', {}).get('installed') for e in result['environments'].values()) or args.variant == 'sglang'
    for name, spec in m['retained_sources'].items():
        path = Path(spec['path'])
        assert run(['git', '-c', f'safe.directory={path}', '-C', str(path), 'rev-parse', 'HEAD']) == spec['ref'], name
    sdk_source = ROOT / 'sdk' / 'candidate.so'
    assert digest(sdk_source) == m['sdk']['sha256']
    sdk_targets = [Path('/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocprofiler-sdk.so.1'), Path('/opt/rocm/core-10.0/lib/librocprofiler-sdk.so.1.3.5')]
    for destination in sdk_targets:
        assert destination.is_file(), destination
        assert destination.resolve().is_relative_to(Path('/opt'))
        if not args.verify_only:
            shutil.copyfile(sdk_source, destination)
        assert digest(destination) == m['sdk']['sha256'], destination
    result['sdk_sha256'] = m['sdk']['sha256']
    # The CLI source and all installed executable bytes remain separately bound.
    if not args.verify_only:
        run([sys.executable, str(ROOT / 'install-native-agent-runtime.py')])
    result['native_agent'] = json.loads(run([sys.executable, str(ROOT / 'install-native-agent-runtime.py'), '--verify-only']))
    assert run(['/opt/haloloom/codex-amd/bin/codex', '--version']) == 'codex-cli 0.156.1'
    if args.variant in {'vllm', 'quark'}:
        vllm = TARGETS['vllm']
        required = ['vllm/config/profiler.py','vllm/profiler/tracelens.py','vllm/profiler/wrapper.py','vllm/v1/worker/encoder_cudagraph.py','vllm/v1/worker/gpu/cudagraph_utils.py','vllm/v1/worker/gpu/model_runner.py','vllm/v1/worker/gpu_worker.py']
        descriptor = {'schema':'hyperloom.vllm.tracelens.install.v1','execution_schema':'vllm.tracelens.execution.v1','version':result['environments']['/opt/venv/bin/python']['vllm']['version'],'files':{rel:digest(vllm / rel) for rel in required}}
        path = Path('/opt/haloloom/vllm-tracelens-install.json')
        if not args.verify_only:
            path.write_text(json.dumps(descriptor, indent=2)+'\n')
        assert json.loads(path.read_text()) == descriptor
    # Keep reinstallable mirrors aligned, not just live site-packages.
    if not args.verify_only:
        names = {n.lower().replace('_','-') for n in DISTRIBUTIONS.values()}
        for mirrors in [Path('/opt/haloloom/wheels'), Path('/opt/qwen38-21ee-wheels')]:
            if not mirrors.exists():
                continue
            for old in mirrors.glob('*.whl'):
                with zipfile.ZipFile(old) as archive:
                    metadata = [n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
                    assert len(metadata) == 1, old
                    name = email.message_from_bytes(archive.read(metadata[0]))['Name'].lower().replace('_','-')
                if name in names:
                    old.unlink()
            for name, spec in m['components'].items():
                if mirrors.name == 'qwen38-21ee-wheels' and name != 'vllm':
                    continue
                shutil.copyfile(ROOT/'wheels'/spec['wheel'], mirrors/spec['wheel'])
    for mirrors in [Path('/opt/haloloom/wheels'), Path('/opt/qwen38-21ee-wheels')]:
        if not mirrors.exists():
            continue
        for name, spec in m['components'].items():
            if mirrors.name == 'qwen38-21ee-wheels' and name != 'vllm':
                continue
            assert digest(mirrors/spec['wheel']) == digest(ROOT/'wheels'/spec['wheel'])
    result['status'] = 'PASS_SOURCE_AND_INSTALLED_PAYLOAD'
    result['gpu_qualified'] = False
    result['promotion_authority'] = False
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
