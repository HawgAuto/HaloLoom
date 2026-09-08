"""CPU packaging regressions; fixture SDK is not GPU qualification."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install_bundled_amdsmi.py'


def helper():
    assert SCRIPT.is_file(), 'Bundled AMD SMI must be registered in the installed interpreter, not only PYTHONPATH'
    spec = importlib.util.spec_from_file_location('bundled_smi_packaging', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sdk(root):
    package = root / '_rocm_sdk_core/share/amd_smi/amdsmi'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('FIXTURE = True\n')
    return package


def test_scrubbed_interpreter_imports_only_bundled_sdk(tmp_path):
    module = helper()
    envroot = tmp_path / 'venv'
    venv.EnvBuilder(with_pip=False).create(envroot)
    python = envroot / 'bin/python'
    purelib = Path(subprocess.check_output([str(python), '-I', '-c',
        'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip())
    package = sdk(purelib)
    hostile = tmp_path / 'hostile'; hostile.mkdir()
    sentinel = tmp_path / 'foreign_executed'
    (hostile / 'amdsmi.py').write_text(f'from pathlib import Path\nPath({str(sentinel)!r}).touch()\n')
    before = subprocess.run([str(python), '-I', '-c', 'import amdsmi'], capture_output=True)
    assert before.returncode != 0 and b'No module named' in before.stderr
    result = module.install_bundled_amdsmi(purelib)
    assert result['status'] == 'registered'
    env = {**os.environ, 'PYTHONPATH': str(hostile)}
    after = subprocess.run([str(python), '-I', '-c',
        'import amdsmi,json; print(json.dumps({"path":amdsmi.__file__,"fixture":amdsmi.FIXTURE}))'],
        env=env, cwd=hostile, capture_output=True, text=True)
    assert after.returncode == 0, after.stderr
    assert json.loads(after.stdout) == {'path': str(package / '__init__.py'), 'fixture': True}
    assert not sentinel.exists()
    pth = Path(result['pth'])
    assert pth.read_text() == '_rocm_sdk_core/share/amd_smi\n'
    assert module.install_bundled_amdsmi(purelib, verify_only=True) == result


@pytest.mark.parametrize('kind', ['package_parent', 'source', 'pth'])
def test_symlink_rejected_before_registration(tmp_path, kind):
    module = helper(); package = sdk(tmp_path)
    foreign = tmp_path / 'foreign'; foreign.mkdir()
    target = foreign / 'keep.txt'
    if kind == 'package_parent':
        original = package.parent
        moved = foreign / 'amd_smi'; original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)
    elif kind == 'source':
        source = foreign / 'extra.py'; source.write_text('UNTRUSTED = True\n')
        (package / 'extra.py').symlink_to(source)
    else:
        target.write_text('unchanged\n')
        (tmp_path / 'haloloom_bundled_amdsmi.pth').symlink_to(target)
    with pytest.raises((ValueError, RuntimeError), match='symlink'):
        module.install_bundled_amdsmi(tmp_path)
    if kind == 'pth': assert target.read_text() == 'unchanged\n'
    else: assert not (tmp_path / 'haloloom_bundled_amdsmi.pth').exists()


def test_missing_sdk_is_explicitly_not_applicable(tmp_path):
    assert helper().install_bundled_amdsmi(tmp_path)['status'] == 'not_applicable_no_modular_sdk'
    assert not list(tmp_path.iterdir())


def test_incomplete_bundled_sdk_fails_closed(tmp_path):
    (tmp_path / '_rocm_sdk_core').mkdir()
    with pytest.raises((ValueError, RuntimeError), match='AMD SMI'):
        helper().install_bundled_amdsmi(tmp_path)


def test_verify_only_never_creates_registration(tmp_path):
    sdk(tmp_path)
    with pytest.raises((ValueError, RuntimeError), match='registration'):
        helper().install_bundled_amdsmi(tmp_path, verify_only=True)
    assert not (tmp_path / 'haloloom_bundled_amdsmi.pth').exists()


def test_foreign_registration_is_not_overwritten(tmp_path):
    sdk(tmp_path)
    pth = tmp_path / 'haloloom_bundled_amdsmi.pth'; pth.write_text('/foreign\n')
    with pytest.raises((ValueError, RuntimeError), match='registration'):
        helper().install_bundled_amdsmi(tmp_path)
    assert pth.read_text() == '/foreign\n'


def test_supported_image_recipe_registers_the_source_bound_helper():
    recipe = (SCRIPT.parents[1] / 'docker/source-current/Dockerfile').read_text()
    assert '/opt/haloloom/source-current/install_bundled_amdsmi.py' in recipe
    assert '--report /opt/haloloom/bundled-amdsmi.json' in recipe
