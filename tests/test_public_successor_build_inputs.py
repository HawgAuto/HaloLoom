"""CPU-only schema 3 public successor contract; Docker and HTTPS are mocked."""
import hashlib
import io
import json
import subprocess
import tarfile

import pytest
from test_public_build_inputs import build_inputs, make_tar, write_manifest
from test_candidate_build_inputs import packet


@pytest.fixture(autouse=True)
def forbid_external(monkeypatch):
    monkeypatch.setattr(build_inputs.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('unexpected network'))
    monkeypatch.setattr(build_inputs.subprocess, 'run', lambda *a, **k: pytest.fail('unexpected Docker action'))


def successor(tmp_path, monkeypatch, **kwargs):
    archive, data = packet(tmp_path, **kwargs)
    data.update(schema_version=3, version='v0.1.2')
    data['overlay_archive']['url'] = 'https://example.test/releases/v0.1.2/' + archive.name
    for name, row in data['images'].items():
        row['local_tag'] = f'haloloom-{name}:v0.1.2-test'
    class Response(io.BytesIO):
        def geturl(self):
            return data['overlay_archive']['url']
    def urlopen(request, *, timeout):
        assert request.full_url == data['overlay_archive']['url']
        assert timeout == build_inputs.DOWNLOAD_TIMEOUT_SECONDS
        return Response(archive.read_bytes())
    class Opener:
        open = staticmethod(urlopen)
    monkeypatch.setattr(build_inputs.urllib.request, 'build_opener', lambda *handlers: Opener())
    return archive, data


@pytest.mark.parametrize('version', ['v0.1.2', 'v1.0.0', 'v12.34.56-rc1', 'v0.1.2-rc0'])
def test_accepts_release_versions(tmp_path, monkeypatch, version):
    _, data = successor(tmp_path, monkeypatch)
    data['version'] = version
    assert build_inputs.validate_manifest(data) == data


@pytest.mark.parametrize('field,value', [
    *[('schema_version', v) for v in [True, False, 3.0, 2.0, 1.0, '3', None, 0, 1, 2, 4]],
    *[('version', v) for v in [True, 3, None, 'v0.1.1', 'candidate-a', 'latest', 'v01.2.3',
       'v1.02.3', 'v1.2.03', 'v1.2', '1.2.3', 'v1.2.3-rc', 'v1.2.3-rc01', 'v1.2.3+meta', 'v1.2.3\n']],
    ('sources', True), ('images', []), ('overlay_archive', None),
])
def test_rejects_types_and_versions(tmp_path, monkeypatch, field, value):
    _, data = successor(tmp_path, monkeypatch)
    data[field] = value
    with pytest.raises(build_inputs.InputError):
        build_inputs.validate_manifest(data)


@pytest.mark.parametrize('value', [True, False, 1.0, '1'])
def test_schema1_rejects_downgraded_schema_type(tmp_path, monkeypatch, value):
    _, data = successor(tmp_path, monkeypatch)
    data.pop('sources'); data.update(schema_version=value, version='v0.1.1')
    with pytest.raises(build_inputs.InputError):
        build_inputs.validate_manifest(data)


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(extra=False), lambda d: d.pop('sources'),
    lambda d: d['sources'].pop('GEAK'), lambda d: d['sources'].update(extra={}),
    lambda d: d['sources']['GEAK'].update(extra=False),
    *[lambda d, v=v: d['sources']['GEAK'].update(ref=v) for v in [True, None, 'main', 'A'*40, 'a'*39]],
    lambda d: d['sources']['HaloLoom'].update(tree='F'*40),
    *[lambda d, v=v: d['overlay_archive'].update(url=v) for v in [True, 'http://example.test/candidate.tgz',
      'https://user@example.test/candidate.tgz', 'https://example.test/candidate.tgz?q=1',
      'https://example.test/candidate.tgz#x', 'https://example.test/other.tgz']],
    *[lambda d, v=v: d['overlay_archive'].update(filename=v, url='https://example.test/'+str(v))
      for v in ['../candidate.tgz', '/candidate.tgz', 'x\\y.tgz', '-x.tgz', 'x\n.tgz', 'x.zip', True]],
    *[lambda d, v=v: d['overlay_archive'].update(sha256=v) for v in [True, 'A'*64, 'a'*63]],
    lambda d: d['images'].pop('quark'), lambda d: d['images'].update(extra={}),
    lambda d: d['images']['vllm'].update(apply_overlay=1),
    lambda d: d['images']['aiter-tools'].update(apply_overlay=True),
    lambda d: d['images']['vllm'].update(base_reference='ghcr.io/a:latest'),
    lambda d: d['images']['quark'].update(local_tag='untagged'),
    lambda d: d['images']['quark'].update(local_tag=d['images']['vllm']['local_tag']),
    lambda d: d['images']['quark'].update(base_reference=d['images']['vllm']['base_reference']),
])
def test_rejects_malformed_contract(tmp_path, monkeypatch, mutate):
    _, data = successor(tmp_path, monkeypatch); mutate(data)
    with pytest.raises(build_inputs.InputError):
        build_inputs.validate_manifest(data)


def docker(monkeypatch, failure=None):
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if command[:3] == ['docker', 'image', 'inspect']:
            if len(commands) == 4 and failure:
                return subprocess.CompletedProcess(command, *failure)
            return subprocess.CompletedProcess(command, 1, '[]\n', 'Error: No such image: '+command[-1]+'\n')
        assert kwargs['check']
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(build_inputs.subprocess, 'run', run)
    return commands


def test_cli_public_successor_full_flow(tmp_path, monkeypatch, capsys):
    archive, data = successor(tmp_path, monkeypatch)
    commands = docker(monkeypatch)
    scripts = tmp_path/'scripts'; scripts.mkdir()
    monkeypatch.setattr(build_inputs, '__file__', str(scripts/'build_release_inputs.py'))
    assert build_inputs.main(['--manifest', str(write_manifest(tmp_path, data)), '--max-unpacked-bytes', '4096']) == 0
    assert 'HALOLOOM_PUBLIC_BUILD_COMPLETE' in capsys.readouterr().out
    assert (tmp_path/'dist/source-current'/archive.name).read_bytes() == archive.read_bytes()
    expected = [['docker', 'image', 'inspect', r['local_tag']] for r in data['images'].values()]
    labels = [f'haloloom.{n.lower()}_ref='+data['sources'][n]['ref'] for n in ['Hyperloom', 'GEAK', 'HaloLoom']]
    labels += ['haloloom.candidate_id=v0.1.2', 'haloloom.promotion_authority=false']
    for name, row in data['images'].items():
        expected.append(['docker', 'pull', row['base_reference']])
        expected.append(['docker', 'build', '--network', 'none', '--target', name, '--build-arg',
                         'BASE_IMAGE='+row['base_reference'], '-f', 'docker/source-current/Dockerfile',
                         '-t', row['local_tag'], *[x for label in labels for x in ['--label', label]], '.']
                        if row['apply_overlay'] else ['docker', 'tag', row['base_reference'], row['local_tag']])
    assert commands == expected


@pytest.mark.parametrize('failure', [(0, '[]', ''), (1, '', 'unauthorized'), (1, '', 'Cannot connect to Docker'),
    (1, '', ''), (125, '', 'Error: No such image: haloloom-aiter-tools:v0.1.2-test'),
    (1, '', 'Error: No such image: wrong'), (1, '{}', 'Error: No such image: haloloom-aiter-tools:v0.1.2-test')])
def test_tag_inspect_fails_closed(tmp_path, monkeypatch, failure):
    _, data = successor(tmp_path, monkeypatch); commands = docker(monkeypatch, failure)
    with pytest.raises(build_inputs.InputError, match='candidate image tag'):
        build_inputs.prepare(write_manifest(tmp_path, data), tmp_path/'stage', root=tmp_path)
    assert len(commands) == 4 and all(c[:3] == ['docker', 'image', 'inspect'] for c in commands)
    assert not (tmp_path/'stage').exists() and not list(tmp_path.glob('.stage.*'))


@pytest.mark.parametrize('kind', ['mismatch', 'duplicate', 'missing', 'invalid', 'boolean', 'hash', 'corrupt',
    'traversal', 'symlink', 'hardlink', 'device', 'duplicate-member', 'unpacked', 'compressed'])
def test_bad_archive_before_any_docker(tmp_path, monkeypatch, kind):
    archive, data = successor(tmp_path, monkeypatch)
    cap = 4096
    entries = [(tarfile.TarInfo('candidate-sources.json'), json.dumps(data['sources']).encode())]
    if kind in ['mismatch', 'duplicate', 'invalid', 'boolean']:
        entries[0] = (entries[0][0], {'mismatch': b'{}', 'duplicate': b'{"GEAK":{},"GEAK":{}}',
                                    'invalid': b'{', 'boolean': b'true'}[kind])
    elif kind == 'missing': entries = []
    elif kind in ['traversal', 'symlink', 'hardlink', 'device']:
        info = tarfile.TarInfo('../escape' if kind == 'traversal' else 'unsafe')
        if kind != 'traversal':
            info.type = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE, 'device': tarfile.CHRTYPE}[kind]
            info.linkname = 'candidate-sources.json'
        entries.append((info, b''))
    elif kind == 'duplicate-member': entries += entries
    elif kind == 'unpacked': entries.append((tarfile.TarInfo('large'), b'x'*5000))
    elif kind == 'compressed': cap = 1
    make_tar(archive, entries)
    if kind == 'corrupt': archive.write_bytes(b'bad gzip')
    data['overlay_archive']['sha256'] = 'f'*64 if kind == 'hash' else hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(build_inputs.InputError):
        build_inputs.prepare(write_manifest(tmp_path, data), tmp_path/'stage', root=tmp_path, max_bytes=cap)
    assert not (tmp_path/'stage').exists() and not list(tmp_path.glob('.stage.*'))


def test_duplicate_manifest_key(tmp_path, monkeypatch):
    _, data = successor(tmp_path, monkeypatch)
    path = write_manifest(tmp_path, data)
    path.write_text(path.read_text().replace('"schema_version": 3', '"schema_version": 3, "schema_version": 3'))
    with pytest.raises(build_inputs.InputError, match='duplicate JSON key'):
        build_inputs.load_manifest(path)


def test_public_rejects_archive_override(tmp_path, monkeypatch):
    archive, data = successor(tmp_path, monkeypatch)
    with pytest.raises(build_inputs.InputError, match='--archive'):
        build_inputs.prepare(write_manifest(tmp_path, data), tmp_path/'stage', root=tmp_path, archive=archive)
