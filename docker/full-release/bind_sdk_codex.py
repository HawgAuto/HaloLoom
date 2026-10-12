#!/usr/bin/env python3
"""Bind SDK-vendored CLI entrypoints to the same qualified native runtime."""
import hashlib,json
from pathlib import Path

ROOT=Path('/opt/haloloom/codex-amd')
PREDECESSORS={'codex':{'cb0a15567e9a60a5820d54b0f6ae86d504dc3805c1eab21a47f70e3eb7b73a40'},
              'codex-code-mode-host':{'00ecf5d040865b97884c488883abd342581c2a432debe7a54e4646bceee3d2d6'}}
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    m=json.loads(Path('/opt/haloloom/source-current/manifest.json').read_text())['native_agent_runtime']
    roots=sorted(Path('/opt').glob('*/lib/python*/site-packages/codex_cli_bin/bin'))
    assert roots,'SDK native entrypoints not found'
    rows=[]
    for directory in roots:
        for name,allowed in PREDECESSORS.items():
            p=directory/name;target=ROOT/'bin'/name
            assert p.is_file() and target.is_file()
            expected=m['files']['bin/'+name];assert sha(target)==expected
            before=sha(p)
            assert before in allowed|{expected},(p,before)
            if p.is_symlink():assert p.resolve()==target.resolve(),p
            else:p.unlink();p.symlink_to(target)
            assert p.resolve()==target.resolve() and sha(p)==expected
            rows.append({'path':str(p),'realpath':str(target),'sha256':expected})
    print(json.dumps({'status':'PASS_SDK_NATIVE_CLI_BINDINGS','source_commit':m['source_commit'],'bindings':rows},indent=2))
if __name__=='__main__':main()
