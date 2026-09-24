#!/usr/bin/env python3
"""Build complete HaloLoom release images from pinned public runtimes and source packets.

Schema 4 verifies the complete archive SHA before parsing it. It permits bounded
in-tree source symlinks; older schema extractors and their stricter format remain
unchanged. No GPU is attached during assembly or source verification.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse

import build_release_inputs as legacy

COMPONENTS = {'GEAK', 'Hyperloom', 'Quark', 'TraceLens', 'vllm'}
VARIANTS = ('vllm', 'quark', 'sglang', 'aiter-tools')
MAX_UNPACKED = 2 << 30
MAX_MEMBERS = 40000
MAX_COMPRESSED = 1 << 30


def validate(value: dict) -> dict:
    legacy._exact_keys(value, {'schema_version', 'version', 'sources', 'overlay_archive', 'images'}, 'full release')
    if type(value['schema_version']) is not int or value['schema_version'] != 4:
        raise ValueError('full release requires schema 4')
    if not isinstance(value['version'], str) or not re.fullmatch(r'v\d+\.\d+\.\d+', value['version']):
        raise ValueError('invalid full release version')
    legacy._exact_keys(value['sources'], COMPONENTS, 'sources')
    for name, source in value['sources'].items():
        legacy._exact_keys(source, {'ref', 'tree'}, name)
        if any(not isinstance(x, str) or not re.fullmatch('[a-f0-9]{40}', x) for x in source.values()):
            raise ValueError('invalid source identity: ' + name)
    asset = legacy._exact_keys(value['overlay_archive'], {'url', 'filename', 'sha256'}, 'archive')
    legacy._require_https_target(asset['url'])
    parsed = urllib.parse.urlsplit(asset['url'])
    if (parsed.query or parsed.fragment or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz', asset['filename'])
            or PurePosixPath(parsed.path).name != asset['filename']
            or not re.fullmatch('[a-f0-9]{64}', asset['sha256'])):
        raise ValueError('invalid archive identity')
    legacy._exact_keys(value['images'], set(VARIANTS), 'images')
    tags = set()
    for name, row in value['images'].items():
        legacy._exact_keys(row, {'base_reference', 'local_tag', 'apply_overlay'}, name)
        if not legacy.BASE_REFERENCE.fullmatch(row['base_reference']) or not legacy.LOCAL_TAG.fullmatch(row['local_tag']):
            raise ValueError('invalid pinned image: ' + name)
        if row['apply_overlay'] is not (name != 'aiter-tools') or row['local_tag'] in tags:
            raise ValueError('invalid image application: ' + name)
        tags.add(row['local_tag'])
    return value


def extract_verified(source: Path, destination: Path, expected: str) -> None:
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_COMPRESSED:
        raise ValueError('archive must be a bounded regular file')
    if legacy._sha256(source) != expected:
        raise ValueError('archive SHA-256 mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    seen = set()
    unpacked = 0
    # Parsing starts only after authenticating the complete trusted release bytes.
    with tarfile.open(source, 'r|gz') as archive:
        for member in archive:
            path = legacy._safe_member_name(member.name)
            if path in seen or len(seen) >= MAX_MEMBERS:
                raise ValueError('duplicate/member limit: ' + member.name)
            seen.add(path)
            if not (member.isreg() or member.isdir() or member.issym()) or member.size < 0:
                raise ValueError('unsupported archive member: ' + member.name)
            unpacked += member.size
            if unpacked > MAX_UNPACKED:
                raise ValueError('unpacked byte limit')
            if member.issym():
                if Path(member.linkname).is_absolute() or not (destination / path.parent / member.linkname).resolve().is_relative_to(destination.resolve()):
                    raise ValueError('escaping source symlink: ' + member.name)
            archive.extract(member, destination, filter='data')


def verify_payload(root: Path, release: dict) -> dict:
    packet = json.loads((root / 'manifest.json').read_text(), object_pairs_hook=legacy._reject_duplicate_keys)
    if packet['schema_version'] != 4 or packet['release'] != release['version'] or set(packet['components']) != COMPONENTS:
        raise ValueError('payload schema, release or components differ')
    for name, expected in release['sources'].items():
        if any(packet['components'][name][k] != v for k, v in expected.items()):
            raise ValueError('source identity differs: ' + name)
    for relative, expected in packet['payload_files'].items():
        path = root / legacy._safe_member_name(relative)
        if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or legacy._sha256(path) != expected:
            raise ValueError('payload file differs: ' + relative)
    return packet


def labels(packet: dict, variant: str) -> dict:
    result = {'haloloom.release': packet['release'], 'haloloom.promotion_authority': 'false',
              'haloloom.rocprofiler_sdk_sha256': packet['sdk']['sha256'],
              'haloloom.codex_version': packet['native_agent_runtime']['version']}
    fields = {'GEAK': 'geak_ref', 'Hyperloom': 'hyperloom_ref', 'Quark': 'quark_ref',
              'TraceLens': 'tracelens_ref', 'vllm': 'vllm_source_ref'}
    for name, field in fields.items():
        result['haloloom.' + field] = packet['components'][name]['ref']
    result['haloloom.vllm_runtime_installed'] = str(variant != 'sglang').lower()
    result['haloloom.vllm_composite_wheel_sha256'] = packet['components']['vllm']['wheel_sha256']
    return result


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(__file__).resolve().parents[1]
    peek = argparse.ArgumentParser(add_help=False)
    peek.add_argument('--manifest', type=Path, default=root / 'manifests/build-inputs.json')
    chosen, _ = peek.parse_known_args(argv)
    path = chosen.manifest if chosen.manifest.is_absolute() else root / chosen.manifest
    raw = json.loads(path.read_text(), object_pairs_hook=legacy._reject_duplicate_keys)
    if raw.get('schema_version') != 4:
        return legacy.main(argv)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, default=path)
    p.add_argument('--archive', type=Path)
    p.add_argument('--output-dir', type=Path, default=root / 'dist/full-release')
    p.add_argument('--prepare-only', action='store_true')
    p.add_argument('--image', choices=VARIANTS, action='append')
    p.add_argument('--package-quark-native', action='store_true', help='native Quark is already bound in the qualified base')
    args = p.parse_args(argv)
    release = validate(raw)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    asset = release['overlay_archive']
    source = args.archive.resolve() if args.archive else out / asset['filename']
    if args.archive is None:
        legacy.download_successor_https(asset['url'], source, MAX_COMPRESSED)
    extract_verified(source, out / 'payload', asset['sha256'])
    packet = verify_payload(out / 'payload', release)
    context = out / 'context'
    context.mkdir()
    shutil.copyfile(source, context / 'full-release-inputs.tar.gz')
    shutil.copyfile(root / 'docker/full-release/Dockerfile', context / 'Dockerfile')
    shutil.copyfile(root / 'docker/quark/plugin-entrypoint', context / 'plugin-entrypoint')
    result = {'schema': 4, 'version': release['version'], 'payload_sha256': asset['sha256'],
              'payload_files_verified': len(packet['payload_files']), 'images': {}, 'published': False}
    for variant in args.image or VARIANTS:
        row = release['images'][variant]
        target = row['local_tag']
        if args.prepare_only:
            result['images'][variant] = {'base_reference': row['base_reference'], 'target': target, 'executed': False}
            continue
        if subprocess.run(['docker', 'image', 'inspect', target], capture_output=True).returncode == 0:
            raise ValueError('refusing to overwrite image: ' + target)
        subprocess.run(['docker', 'pull', row['base_reference']], check=True)
        if not row['apply_overlay']:
            subprocess.run(['docker', 'tag', row['base_reference'], target], check=True)
            continue
        applied = target + '-applied'
        subprocess.run(['docker', 'build', '--pull=false', '--network=none', '--build-arg', 'BASE_IMAGE=' + row['base_reference'],
                        '--build-arg', 'VARIANT=' + variant, '--build-arg', 'PAYLOAD_SHA256=' + asset['sha256'],
                        '-t', applied, str(context)], check=True)
        command = [sys.executable, str(root / 'scripts/compact_codex_image.py'), applied, target,
                   '--verify-ecosystem', '--recipe-out', str(out / (variant + '-compact.Dockerfile'))]
        for key, value in labels(packet, variant).items():
            command += ['--label', key + '=' + value]
        subprocess.run(command, check=True)
        subprocess.run(['docker', 'run', '--rm', '--network=none', target, 'verify'], check=True)
        result['images'][variant] = json.loads(subprocess.check_output(['docker', 'image', 'inspect', target], text=True))[0]['Id']
    (out / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print('Full release build failed: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
