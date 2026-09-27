#!/usr/bin/env python3
"""Overlay exact Python source onto a recorded native vLLM donor wheel.

This does not rebuild or relabel the donor's native extensions. Their complete
byte identity is checked and retained in the sidecar receipt.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compose(donor: Path, source: Path, output: Path, receipt: Path) -> dict:
    if output.exists() or receipt.exists():
        raise ValueError('Output/receipt already exists')
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z'], text=True).split('\0')
    roots = {'quark_mixed_moe.py', 'mtp_dense.py', 'mtp_checkpoint.py', 'native_wire_binding.py'}
    overrides = {p: (source / p).read_bytes() for p in tracked if p and p.endswith('.py') and (p.startswith('vllm/') or p in roots)}
    assert roots.issubset(overrides)
    generated = 'vllm/_haloloom_source.json'
    overrides[generated] = (json.dumps({'source_commit': commit, 'native_binary_rebuilt': False, 'donor_sha256': sha(donor.read_bytes())}, sort_keys=True)+'\n').encode()
    binary_before = {}
    members = {}
    infos = {}
    with zipfile.ZipFile(donor) as z:
        for info in z.infolist():
            name = info.filename
            if name.startswith('/') or '..' in Path(name).parts or name in members:
                raise ValueError('Unsafe or duplicate wheel member')
            if info.is_dir():
                continue
            members[name] = z.read(name)
            infos[name] = info
            if name.endswith('.so'):
                binary_before[name] = sha(members[name])
    assert binary_before, 'Expected a real native donor wheel'
    record_names = [n for n in members if n.endswith('.dist-info/RECORD')]
    assert len(record_names) == 1
    record = record_names[0]
    members.update(overrides)
    rows = []
    for name, data in sorted(members.items()):
        if name != record:
            rows.append([name, 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), str(len(data))])
    rows.append([record, '', ''])
    stream = io.StringIO(newline='')
    csv.writer(stream).writerows(rows)
    members[record] = stream.getvalue().encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in sorted(members.items()):
            if name in infos:
                info = infos[name]
                info.compress_type = zipfile.ZIP_DEFLATED
            else:
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(output) as z:
        assert {n: sha(z.read(n)) for n in z.namelist() if n.endswith('.so')} == binary_before
        for name, data in overrides.items():
            assert z.read(name) == data
    result = {'source_commit': commit, 'donor_sha256': sha(donor.read_bytes()), 'wheel_sha256': sha(output.read_bytes()), 'wheel': output.name, 'native_binary_rebuilt': False, 'native_members': binary_before, 'source_members': {n: sha(v) for n, v in overrides.items()}, 'record_rebuilt': True}
    receipt.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    result=compose(args.donor,args.source,args.output,args.receipt)
    print(json.dumps({k: v for k, v in result.items() if k not in ['native_members','source_members']}, sort_keys=True))


if __name__ == '__main__':
    main()
