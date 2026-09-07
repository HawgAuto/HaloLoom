"""Behavioral regressions: real urllib handlers, no sockets or Docker."""
import gzip
import io
import tarfile
import urllib.response

import pytest
from test_public_build_inputs import build_inputs as b, make_tar


def transport(monkeypatch, routes):
    contacted = []
    class Transport(b.urllib.request.BaseHandler):
        handler_order = 100
        def https_open(self, req):
            contacted.append(req.full_url)
            status, headers, body = routes[req.full_url]
            response = urllib.response.addinfourl(io.BytesIO(body), headers, req.full_url, status)
            response.msg = 'Found' if status == 302 else 'OK'
            return response
        http_open = https_open
    original = b.urllib.request.build_opener
    def build(*handlers):
        return original(b.urllib.request.ProxyHandler({}), Transport(), *handlers)
    monkeypatch.setattr(b.urllib.request, 'build_opener', build)
    monkeypatch.setattr(b.urllib.request, 'urlopen', build().open)
    return contacted


@pytest.mark.parametrize('target', [
    'http://bad.test/a', '//user:password@bad.test/a',
    'https://@bad.test/a', 'https://user@bad.test/a',
    'http://bad.test/a?next=https://good.test/a',
])
@pytest.mark.parametrize('intermediate', [False, True])
def test_redirect_target_never_dispatched(tmp_path, monkeypatch, target, intermediate):
    start = 'https://github.com/a'
    middle = 'https://signed.test/a?signature=ok'
    routes = {start: (302, {'location': middle if intermediate else target}, b''),
              middle: (302, {'location': target}, b'')}
    # Unsafe dispatch returns to HTTPS, hiding the downgrade from final-URL checks.
    resolved = b.urllib.parse.urljoin(middle if intermediate else start, target)
    routes[resolved] = (302, {'location': 'https://good.test/a'}, b'')
    routes['https://good.test/a'] = (200, {}, b'ok')
    contacted = transport(monkeypatch, routes)
    with pytest.raises(b.InputError):
        getattr(b, 'download_successor_https', b.download_https)(start, tmp_path/'download')
    assert contacted == ([start, middle] if intermediate else [start])


@pytest.mark.parametrize('target', ['/asset?sig=abc', '//release-assets.githubusercontent.com/asset?sig=abc'])
def test_signed_https_redirect_allowed(tmp_path, monkeypatch, target):
    start = 'https://github.com/a'
    final = b.urllib.parse.urljoin(start, target)
    contacted = transport(monkeypatch, {start: (302, {'location': target}, b''),
                                         final: (200, {}, b'ok')})
    getattr(b, 'download_successor_https', b.download_https)(start, tmp_path/'download')
    assert contacted == [start, final]
    assert (tmp_path/'download').read_bytes() == b'ok'


def extract(path, dest, cap=4096):
    getattr(b, 'extract_successor_archive', b.extract_archive)(path, dest, cap)


@pytest.mark.parametrize('kind', ['pax', 'longname', 'directories', 'empty', 'payload', 'gzip-tail'])
def test_tar_bounds_before_side_effects(tmp_path, monkeypatch, kind):
    path = tmp_path/'archive.tgz'
    if kind in ('pax', 'longname'):
        with tarfile.open(path, 'w:gz', format=tarfile.PAX_FORMAT if kind == 'pax' else tarfile.GNU_FORMAT) as tar:
            info = tarfile.TarInfo('empty' if kind == 'pax' else 'x'*(2*1024*1024))
            if kind == 'pax':
                info.pax_headers = {'comment': 'x'*(2*1024*1024)}
            tar.addfile(info)
    elif kind in ('directories', 'empty'):
        entries = []
        for i in range(1025):
            info = tarfile.TarInfo(str(i))
            if kind == 'directories':
                info.type = tarfile.DIRTYPE
            entries.append((info, b''))
        make_tar(path, entries)
    elif kind == 'payload':
        make_tar(path, [(tarfile.TarInfo('a'), b'a'*3000), (tarfile.TarInfo('b'), b'b'*3000)])
    else:
        make_tar(path, [(tarfile.TarInfo('a'), b'a')])
        path.write_bytes(path.read_bytes() + gzip.compress(b'\0'*(2*1024*1024)))
    # Instrument metadata parser: oversized metadata must never reach tarfile.
    original = tarfile.TarInfo._proc_pax
    def pax(self, archive):
        assert self.size <= 65536, 'oversized metadata reached parser'
        return original(self, archive)
    monkeypatch.setattr(tarfile.TarInfo, '_proc_pax', pax)
    dest = tmp_path/'extract'
    with pytest.raises(b.InputError):
        extract(path, dest)
    assert not dest.exists()


def test_standard_padding_and_small_pax(tmp_path):
    path = tmp_path/'archive.tgz'
    with tarfile.open(path, 'w:gz') as tar:
        info = tarfile.TarInfo('a')
        info.size = 1
        info.pax_headers = {'comment': 'ordinary metadata'}
        tar.addfile(info, io.BytesIO(b'a'))
    assert len(gzip.decompress(path.read_bytes())) == 10240
    extract(path, tmp_path/'extract', 1)
    assert (tmp_path/'extract/a').read_bytes() == b'a'


@pytest.mark.parametrize('kind', ['pax', 'longname'])
def test_oversized_metadata_body_is_not_consumed(tmp_path, monkeypatch, kind):
    path = tmp_path/'archive.tgz'
    with tarfile.open(path, 'w:gz', format=tarfile.PAX_FORMAT if kind == 'pax' else tarfile.GNU_FORMAT) as tar:
        info = tarfile.TarInfo('a' if kind == 'pax' else 'x'*(2*1024*1024))
        if kind == 'pax':
            info.pax_headers = {'comment': 'x'*(2*1024*1024)}
        tar.addfile(info)
    consumed = []
    original = gzip.GzipFile.read
    def read(self, size=-1):
        data = original(self, size)
        consumed.append(len(data))
        return data
    monkeypatch.setattr(gzip.GzipFile, 'read', read)
    with pytest.raises(b.InputError):
        extract(path, tmp_path/'extract')
    assert sum(consumed) == 512
    assert not (tmp_path/'extract').exists()


@pytest.mark.parametrize('unsafe', [False, True])
def test_prepare_reaches_real_secure_transport(tmp_path, monkeypatch, unsafe):
    import subprocess
    from test_candidate_build_inputs import packet
    from test_public_build_inputs import write_manifest
    archive, data = packet(tmp_path)
    data.update(schema_version=3, version='v0.1.2')
    start = 'https://github.com/releases/' + archive.name
    final = ('http://bad.test/' if unsafe else 'https://release-assets.githubusercontent.com/') + archive.name + '?sig=ok'
    data['overlay_archive']['url'] = start
    contacted = transport(monkeypatch, {start: (302, {'location': final}, b''),
                                         final: (200, {}, archive.read_bytes())})
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if command[:3] == ['docker', 'image', 'inspect']:
            return subprocess.CompletedProcess(command, 1, '[]', 'Error: No such image: '+command[-1])
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(b.subprocess, 'run', run)
    stage = tmp_path/'stage'
    if unsafe:
        with pytest.raises(b.InputError):
            b.prepare(write_manifest(tmp_path, data), stage, root=tmp_path, max_bytes=4096)
        assert contacted == [start]
        assert not commands and not stage.exists() and not list(tmp_path.glob('.stage.*'))
    else:
        b.prepare(write_manifest(tmp_path, data), stage, root=tmp_path, max_bytes=4096)
        assert contacted == [start, final]
        assert (stage/archive.name).read_bytes() == archive.read_bytes()
        assert len(commands) == 12


@pytest.mark.parametrize('metadata', [
    {'GNU.sparse.map': '0,0'},
    {'GNU.sparse.size': '0'},
    {'GNU.sparse.major': '1', 'GNU.sparse.minor': '0'},
])
def test_sparse_metadata_cannot_trigger_secondary_unbounded_parser(tmp_path, metadata):
    path = tmp_path/'archive.tgz'
    with tarfile.open(path, 'w:gz') as tar:
        info = tarfile.TarInfo('empty')
        info.pax_headers = metadata
        tar.addfile(info)
    with pytest.raises(b.InputError, match='sparse'):
        extract(path, tmp_path/'extract')
    assert not (tmp_path/'extract/empty').exists()
