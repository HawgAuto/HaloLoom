# syntax=docker/dockerfile:1.7
FROM haloloom-vllm-full-gfx1151:v0.1.0-rc1

ARG VLLM_WHEEL_SHA256
ARG LOWBIT_WHEEL_SHA256
ARG ACTIVE_RUNTIME_SHA256=7d082d7adb59c0afd51c63790410e03d40adf31b1dc03c0611ab62629055c1a3
COPY dist/frameworks/vllm-full-composite/vllm-*.whl /opt/haloloom/wheels/
COPY dist/frameworks/vllm-full-composite/code-objects.json /opt/haloloom/vllm-full-code-objects.json
COPY dist/lowbit/strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl /opt/haloloom/wheels/
RUN framework="$(find /opt/haloloom/wheels -maxdepth 1 -name 'vllm-*.whl' -print -quit)" \
    && test -n "$framework" -a -n "$VLLM_WHEEL_SHA256" -a -n "$LOWBIT_WHEEL_SHA256" -a -n "$ACTIVE_RUNTIME_SHA256" \
    && echo "$VLLM_WHEEL_SHA256  $framework" | sha256sum --check --strict \
    && echo "$LOWBIT_WHEEL_SHA256  /opt/haloloom/wheels/strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl" | sha256sum --check --strict \
    && /opt/venv/bin/python3 -m pip freeze --all > /tmp/freeze-before \
    && /opt/venv/bin/python3 -m pip install --no-index --no-deps --force-reinstall \
       "$framework" \
       /opt/haloloom/wheels/strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl \
    && install -m 0644 /opt/venv/lib/python3.14/site-packages/hyperloom_rdna35_runtime.py /opt/hyperloom-runtime/hyperloom_rdna35_runtime.py \
    && echo "$ACTIVE_RUNTIME_SHA256  /opt/hyperloom-runtime/hyperloom_rdna35_runtime.py" | sha256sum --check --strict \
    && /opt/venv/bin/python3 -m pip freeze --all > /tmp/freeze-after \
    && /opt/venv/bin/python3 - <<'PY'
from importlib.metadata import version
from pathlib import Path
import importlib.util,inspect,json
before=Path('/tmp/freeze-before').read_text().splitlines(); after=Path('/tmp/freeze-after').read_text().splitlines()
def keep(row):
 name=row.split(' @ ',1)[0].split('==',1)[0].lower().replace('_','-')
 return name not in {'vllm','strix-halo-lowbit-kernel-pack'}
assert sorted(row for row in before if keep(row))==sorted(row for row in after if keep(row))
assert version('vllm')=='0.27.0+haloloom.full.gfx1151.rocm10.rocm100'
assert version('strix-halo-lowbit-kernel-pack')=='0.1.0'
assert importlib.util.find_spec('vllm.model_executor.layers.quantization.gfx1151_lowbit') is not None
assert importlib.util.find_spec('vllm.model_executor.layers.quantization.gfx1151_w4a4_archive') is not None
assets=Path('/opt/venv/lib/python3.14/site-packages/vllm/model_executor/layers/quantization/gfx1151_archive_assets')
assert assets.is_dir() and len(list(assets.glob('*.so')))==4
from hyperloom.inference_optimizer.rdna35_lowbit_hip import load_packaged_hip_module_manifest
from hyperloom.inference_optimizer.rdna35_lowbit_hip import HipModuleRuntime
import hyperloom_rdna35_runtime as active_runtime
module=load_packaged_hip_module_manifest()
assert module.sha256=='404cc2c0c49669cadb2be43326b7a3208c1e3e832ff77c6fd614238bbb9b0983'
assert module.qualification_sha256=='da7b2092176f108548e8d421c76026083da05d5b9df278837d3490af17f1a2e3'
assert Path(active_runtime.__file__).resolve()==Path('/opt/hyperloom-runtime/hyperloom_rdna35_runtime.py')
assert 'asynchronous' in inspect.signature(HipModuleRuntime.launch_linear).parameters
assert hasattr(HipModuleRuntime,'complete_stream')
assert hasattr(active_runtime,'bind_single_lowbit_request')
audit=json.loads(Path('/opt/haloloom/vllm-full-code-objects.json').read_text()); assert audit['all_targets']==['gfx1151']
print('HALOLOOM_VLLM_FULL_RELEASE_STATIC_OK')
PY

LABEL haloloom.lowbit_overlay="strix-halo-lowbit-kernel-pack-0.1.0" \
      haloloom.lowbit_overlay_sha256="${LOWBIT_WHEEL_SHA256}" \
      haloloom.active_lowbit_runtime_sha256="${ACTIVE_RUNTIME_SHA256}" \
      haloloom.vllm_composite_wheel_sha256="${VLLM_WHEEL_SHA256}" \
      haloloom.golden_compact_image_id="sha256:7d5d5ad60610493a79c6ee1070f01821249f4d2f6b4f399554e2232b6a5197d1" \
      haloloom.promotion_authority="false"
