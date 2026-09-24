"""CPU-only release transport tests; fixtures are not runtime qualification."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'scripts/build_full_release_inputs.py'


def api():
    assert MODULE.is_file(), 'the full-release public build consumer is missing'
    sys.path.insert(0, str(MODULE.parent))
    spec = importlib.util.spec_from_file_location('full_release_inputs_tested', MODULE)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def manifest():
    return {'schema_version': 4, 'version': 'v0.1.4',
            'sources': {n: {'ref': 'a' * 40, 'tree': 'b' * 40}
                        for n in ['GEAK', 'Hyperloom', 'Quark', 'TraceLens', 'vllm']},
            'overlay_archive': {'filename': 'full-release-inputs.tar.gz', 'sha256': 'c' * 64,
                                'url': 'https://github.com/HawgAuto/HaloLoom/releases/download/v0.1.4/full-release-inputs.tar.gz'},
            'images': {n: {'base_reference': 'ghcr.io/example/' + n + '@sha256:' + 'd' * 64,
                           'local_tag': 'example/' + n + ':rebuilt', 'apply_overlay': n != 'aiter-tools'}
                       for n in ['vllm', 'quark', 'sglang', 'aiter-tools']}}


def archive(path, members):
    with tarfile.open(path, 'w:gz') as tar:
        for name, body, link in members:
            info = tarfile.TarInfo(name)
            if link is not None:
                info.type = tarfile.SYMTYPE
                info.linkname = link
                tar.addfile(info)
            else:
                data = body.encode()
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))


def test_accepts_complete_source_set():
    assert api().validate(manifest())['schema_version'] == 4


@pytest.mark.parametrize('bad', ['vllm', 'Quark', 'TraceLens'])
def test_rejects_incomplete_source_set(bad):
    data = manifest()
    del data['sources'][bad]
    with pytest.raises(ValueError):
        api().validate(data)


def test_rejects_unpinned_registry_base():
    data = manifest()
    data['images']['quark']['base_reference'] = 'ghcr.io/example/quark:latest'
    with pytest.raises(ValueError):
        api().validate(data)


def test_rejects_archive_hash_mismatch(tmp_path):
    source = tmp_path / 'input.tar.gz'
    archive(source, [('file', 'real fixture bytes', None)])
    with pytest.raises(ValueError, match='SHA'):
        api().extract_verified(source, tmp_path / 'out', '0' * 64)
    assert not (tmp_path / 'out').exists()


def test_internal_source_symlink_survives(tmp_path):
    source = tmp_path / 'input.tar.gz'
    archive(source, [('source/target', 'source fixture', None), ('source/link', '', 'target')])
    api().extract_verified(source, tmp_path / 'out', hashlib.sha256(source.read_bytes()).hexdigest())
    assert (tmp_path / 'out/source/link').is_symlink()
    assert (tmp_path / 'out/source/link').read_text() == 'source fixture'


@pytest.mark.parametrize('name,link', [('../escape', None), ('source/link', '../../escape')])
def test_rejects_escaping_archive(tmp_path, name, link):
    source = tmp_path / 'input.tar.gz'
    archive(source, [(name, 'fixture', link)])
    with pytest.raises((ValueError, tarfile.FilterError)):
        api().extract_verified(source, tmp_path / 'out', hashlib.sha256(source.read_bytes()).hexdigest())
    assert not (tmp_path / 'escape').exists()


def test_rejects_changed_payload_member(tmp_path):
    root = tmp_path / 'payload'
    root.mkdir()
    (root / 'file').write_text('altered')
    spec = {'components': manifest()['sources'], 'schema_version': 4, 'release': 'v0.1.4',
            'payload_files': {'file': hashlib.sha256(b'original').hexdigest()}}
    (root / 'manifest.json').write_text(json.dumps(spec))
    with pytest.raises(ValueError, match='file'):
        api().verify_payload(root, manifest())
