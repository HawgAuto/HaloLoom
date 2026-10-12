"""The source integrity verifier must not mutate its authenticated Git index."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import pytest

SOURCE=Path(__file__).resolve().parents[1]/'docker/full-release/apply_and_verify.py'
spec=importlib.util.spec_from_file_location('full_release_apply',SOURCE)
assert spec and spec.loader
verifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()

def fixture(tmp_path):
    original=tmp_path/'original';original.mkdir()
    git(original,'init','-q')
    (original/'README.md').write_text('Source-bound fixture.\n')
    git(original,'add','README.md')
    git(original,'-c','user.name=Test Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
    copied=tmp_path/'copied';shutil.copytree(original,copied)
    source={'ref':git(original,'rev-parse','HEAD'),'tree':git(original,'rev-parse','HEAD^{tree}'),
            'files':{'README.md':hashlib.sha256((original/'README.md').read_bytes()).hexdigest()}}
    return copied,source

def test_verified_tree_keeps_index_bytes(tmp_path):
    root,source=fixture(tmp_path);before=(root/'.git/index').read_bytes()
    verifier.verify_tree(root,source)
    verifier.verify_tree(root,source)
    assert (root/'.git/index').read_bytes()==before

def test_dirty_source_rejected_without_index_mutation(tmp_path):
    root,source=fixture(tmp_path);before=(root/'.git/index').read_bytes()
    (root/'README.md').write_text('Changed fixture.\n')
    with pytest.raises(AssertionError):verifier.verify_tree(root,source)
    assert (root/'.git/index').read_bytes()==before
