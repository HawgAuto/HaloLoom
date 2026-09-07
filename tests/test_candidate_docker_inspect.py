"""Real Docker missing-image stdout remains an unambiguous absence."""
import importlib.util
from pathlib import Path
import subprocess
import pytest

spec = importlib.util.spec_from_file_location('candidate_inspect', Path(__file__).parents[1] / 'scripts/build_release_inputs.py')
assert spec and spec.loader
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

@pytest.mark.parametrize('stdout', ['', '[]\n'])
def test_real_docker_no_such_image_accepts_empty_inspect_array(monkeypatch, tmp_path, stdout):
    tag = 'haloloom-vllm:test-unique-candidate'
    def run(argv, **kwargs):
        assert argv == ['docker', 'image', 'inspect', tag]
        return subprocess.CompletedProcess(argv, 1, stdout, f'Error response from daemon: No such image: {tag}\n')
    monkeypatch.setattr(build.subprocess, 'run', run)
    build._require_absent_candidate_tags({'images': {'vllm': {'local_tag': tag}}}, tmp_path)

@pytest.mark.parametrize('stdout', ['[{}]', '{}', 'daemon failed', '[ ] trailing'])
def test_missing_image_never_accepts_other_output(monkeypatch, tmp_path, stdout):
    tag = 'haloloom-vllm:test-unique-candidate'
    monkeypatch.setattr(build.subprocess, 'run', lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, stdout, f'Error response from daemon: No such image: {tag}\n'))
    with pytest.raises(build.InputError):
        build._require_absent_candidate_tags({'images': {'vllm': {'local_tag': tag}}}, tmp_path)
