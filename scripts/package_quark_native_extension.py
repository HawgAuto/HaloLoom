#!/usr/bin/env python3
"""AOT-package Quark's native Torch extension from the installed pinned sources.

Run in the Quark Python/Torch ABI lane during image construction. The upstream
source/spec/flag helpers are authoritative; no device availability is fabricated.
The ROCm target is explicit so Docker builds do not require GPU passthrough.
"""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SETUP = r'''
from pathlib import Path
from setuptools import setup
import torch
import quark
from torch.utils.cpp_extension import BuildExtension
from quark.common.torch_cpp_build_specs import HW_EMULATION_C_MODULE, TORCH_TARGET_VERSION_DEFINE
from quark.common.torch_cpp_build_specs.torch_ops import torch_ops_sources, torch_include_paths
from quark.common.torch_cpp_ext import make_setuptools_extension
assert Path(quark.__file__).resolve().is_relative_to(Path.cwd())
assert torch.version.hip, 'requires matching ROCm PyTorch, not CUDA or CPU Torch'
module = make_setuptools_extension(
    name=HW_EMULATION_C_MODULE,
    sources=torch_ops_sources(use_cuda=True),
    include_paths=torch_include_paths(),
    extra_defines=[TORCH_TARGET_VERSION_DEFINE],
    use_cuda=True,
    debug=False,
)
setup(name='haloloom-quark-native-build', version='0.0.0',
      ext_modules=[module], cmdclass={'build_ext': BuildExtension})
'''


def source_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import torch
    if torch.__version__ != '2.13.0+rocm10.0.0' or not torch.version.hip:
        raise RuntimeError('unexpected Quark Torch/ROCm build; requalify new pins')
    if importlib.metadata.version('amd-quark') != '0.12.post1':
        raise RuntimeError('unexpected Quark version; requalify new source specs')
    if os.environ.get('PYTORCH_ROCM_ARCH') != 'gfx1151':
        raise RuntimeError('explicit gfx1151 build target required')
    spec = importlib.util.find_spec('quark')
    if spec is None or spec.origin is None:
        raise RuntimeError('Quark package is missing from the build interpreter')
    root = Path(spec.origin).parent
    if not str(root).startswith('/opt/quark-venv/'):
        raise RuntimeError('wrong Quark package/interpreter lane')
    before = source_hashes(root)
    if args.output.exists():
        raise RuntimeError('output must be a new empty payload path')
    with tempfile.TemporaryDirectory(prefix='quark-aot-') as tmp:
        stage = Path(tmp)
        shutil.copytree(root, stage / 'quark', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        (stage / 'setup.py').write_text(SETUP)
        env = dict(os.environ, PYTHONPATH=str(stage), PYTHONDONTWRITEBYTECODE='1')
        subprocess.run([sys.executable, 'setup.py', 'build_ext', '--build-lib', str(stage / 'out'),
                        '--build-temp', str(stage / 'objects')], cwd=stage, env=env, check=True)
        relative = Path('torch/kernel/hw_emulation')
        libraries = list((stage / 'out/quark' / relative).glob('_C*.so'))
        if len(libraries) != 1:
            raise RuntimeError('build did not produce exactly one native hw_emulation extension')
        if source_hashes(root) != before:
            raise RuntimeError('build modified the installed source package')
        destination = args.output / root.relative_to('/') / relative / libraries[0].name
        destination.parent.mkdir(parents=True)
        shutil.copyfile(libraries[0], destination)
        destination.chmod(0o644)
        receipt = {'quark_version': importlib.metadata.version('amd-quark'),
                   'torch_version': torch.__version__, 'hip_version': torch.version.hip,
                   'python': sys.version, 'architecture': 'gfx1151',
                   'build_spec': 'quark.common.torch_cpp_build_specs.torch_ops',
                   'source_tree_sha256': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
                   'source_files': len(before), 'installed_source_unchanged': True,
                   'library': '/' + str(destination.relative_to(args.output)),
                   'library_sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
        record = args.output / 'opt/haloloom/quark-native-extension.json'
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
