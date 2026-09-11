"""Opt-in tests of the real final Quark image; never substitutes fake kernels."""
import json
import os
import subprocess
import unittest


@unittest.skipUnless(os.environ.get("HALOLOOM_TEST_QUARK_IMAGE"),
                     "set HALOLOOM_TEST_QUARK_IMAGE to run installed-image gates")
class QuarkNativeExtensionImageTests(unittest.TestCase):
    def test_nonroot_readonly_package_import_without_jit(self):
        code = r'''
import json, os, pathlib
assert os.geteuid() == 1000
import torch
import quark
root = pathlib.Path(quark.__file__).parent
libs = list((root / 'torch/kernel/hw_emulation').glob('_C*.so'))
assert libs, 'Quark image is missing its precompiled hw_emulation library'
assert not os.access(root, os.W_OK), 'package must not require runtime writes'
import quark.torch
ops = [n for n in torch._C._dispatch_get_all_op_names()
       if n.startswith('quark_hw_emulation::')]
assert ops, 'native Quark operators not registered'
print(json.dumps({'uid': os.geteuid(), 'torch': torch.__version__,
                  'libraries': [str(p) for p in libs], 'registered_ops': ops}))
'''
        command = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
                   '--user', '1000:1000', '--tmpfs', '/tmp:rw,nosuid,size=256m',
                   '-e', 'HOME=/tmp', '-e', 'PYTHONDONTWRITEBYTECODE=1',
                   '-e', 'QUARK_BUILD_DISABLE_JIT_FALLBACK=1',
                   # Quark and serving use distinct Python/Torch ABI lanes.
                   '-e', 'LD_LIBRARY_PATH=/opt/quark-venv/lib/python3.12/site-packages/torch/lib:/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib',
                   '--entrypoint', '/opt/quark-venv/bin/python',
                   os.environ['HALOLOOM_TEST_QUARK_IMAGE'], '-c', code]
        result = subprocess.run(command, text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('registered_ops', result.stdout)


if __name__ == '__main__':
    unittest.main()
