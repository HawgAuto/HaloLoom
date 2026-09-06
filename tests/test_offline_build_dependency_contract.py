"""Bind the executed public builder command to its offline release recipe."""
from pathlib import Path
import re
from test_public_build_inputs import build_inputs, manifest, regular_archive, write_manifest


def test_supported_offline_build_has_no_online_dependency_provision(tmp_path, monkeypatch):
    source = regular_archive(tmp_path)
    manifest_path = write_manifest(tmp_path, manifest(source))
    commands = []
    monkeypatch.setattr(build_inputs, 'download_https', lambda url, dest: dest.write_bytes(source.read_bytes()))
    monkeypatch.setattr(build_inputs.subprocess, 'run', lambda command, **kwargs: commands.append(command))
    root = Path(__file__).resolve().parents[1]
    build_inputs.prepare(manifest_path, tmp_path / 'stage', root=root)
    builds = [cmd for cmd in commands if cmd[:2] == ['docker', 'build']]
    assert len(builds) == 3
    for cmd in builds:
        assert cmd[cmd.index('--network') + 1] == 'none'
        recipe = root / cmd[cmd.index('-f') + 1]
        assert recipe == root / 'docker/source-current/Dockerfile'
        text = recipe.read_text().replace('\\\n', ' ')
        assert not re.search(r'\bapt(?:-get)?\s+(?:update|install)\b|\bnpm\b[^\n]*\b(?:ci|install)\b', text), \
            'Immutable offline recipe cannot provision unstaged apt/npm dependencies'
