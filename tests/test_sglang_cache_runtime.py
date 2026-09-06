"""SGLang's current cache root must stay in the writable workspace."""
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]

def test_sglang_compose_sets_its_native_cache_root():
    d=yaml.safe_load((ROOT/'compose.yaml').read_text())
    assert d['services']['sglang']['environment'].get('SGLANG_CACHE_DIR')=='/workspace/.cache/sglang'
    assert 'SGLANG_CACHE_DIR' not in d['services']['vllm']['environment']
    assert 'SGLANG_CACHE_DIR' not in d['services']['quark']['environment']

def test_sglang_image_sets_the_same_cache_root_only_in_sglang_stage():
    text=(ROOT/'docker/source-current/Dockerfile').read_text()
    stage=text.split('FROM source-current AS sglang',1)[1].split('FROM source-current AS quark',1)[0]
    assert 'ENV SGLANG_CACHE_DIR=/workspace/.cache/sglang' in stage
