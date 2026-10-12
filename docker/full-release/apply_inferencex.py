#!/usr/bin/env python3
"""Apply the accepted InferenceX patch over a known public image predecessor."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path('/opt/haloloom/source-current')
REPO=Path('/opt/haloloom/components/InferenceX')
# The published v0.1.3 image contains just the already-accepted concurrency flag.
PARTIAL_V013='5b2a58c4282b9e3627be637e961cee388c59cf695234a269355dadf79c2edc01'

def digest(data):return hashlib.sha256(data).hexdigest()
def git(*args):return subprocess.check_output(['git','-c',f'safe.directory={REPO}','-C',str(REPO),*args])

def main():
    patch_dir=ROOT/'inferencex-patch'
    m=json.loads((patch_dir/'manifest.json').read_text())
    patch=patch_dir/m['patch']
    assert digest(patch.read_bytes())==m['patch_sha256']
    assert git('rev-parse','HEAD').decode().strip()==m['base_ref']
    launcher=REPO/m['launcher'];before=digest(launcher.read_bytes())
    if before!=m['accepted_launcher_sha256']:
        assert before in {m['base_launcher_sha256'],PARTIAL_V013}, 'unrecognized predecessor bytes'
        assert not (REPO/'tests/test_haloloom_benchmark_launcher.py').exists(), 'unexpected existing test payload'
        base=git('show','HEAD:'+m['launcher'])
        assert digest(base)==m['base_launcher_sha256']
        launcher.write_bytes(base)
        git('apply','--check',str(patch))
        git('apply',str(patch))
    assert digest(launcher.read_bytes())==m['accepted_launcher_sha256']
    subprocess.run(['bash','-n',str(launcher)],check=True)
    subprocess.run(['/opt/venv/bin/python','-B','-m','pytest','--confcutdir='+str(REPO/'tests'),str(REPO/'tests/test_haloloom_benchmark_launcher.py'),'-q','-p','no:cacheprovider'],check=True,cwd=REPO)
    print(json.dumps({'status':'PASS_ACCEPTED_INFERENCEX_PATCH','predecessor_sha256':before,'accepted_sha256':m['accepted_launcher_sha256'],'source_base':m['base_ref'],'patch_sha256':m['patch_sha256']}))

if __name__=='__main__':main()
