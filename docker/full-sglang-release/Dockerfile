# syntax=docker/dockerfile:1.7
FROM haloloom-sglang-full-gfx1151:v0.1.0-rc1

ARG LOWBIT_WHEEL_SHA256
COPY dist/lowbit/strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl /opt/haloloom/wheels/
RUN test -n "$LOWBIT_WHEEL_SHA256" \
    && echo "$LOWBIT_WHEEL_SHA256  /opt/haloloom/wheels/strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl" | sha256sum --check --strict \
    && /opt/venv/bin/python3 -m pip freeze --all > /tmp/freeze-before \
    && /opt/venv/bin/python3 -m pip install --no-index --no-deps \
       /opt/haloloom/wheels/strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl \
    && /opt/venv/bin/python3 -m pip freeze --all > /tmp/freeze-after \
    && /opt/venv/bin/python3 - <<'PY'
from importlib.metadata import version
from pathlib import Path
import importlib.util, json
before=Path('/tmp/freeze-before').read_text().splitlines()
after=Path('/tmp/freeze-after').read_text().splitlines()
def keep(row): return not row.lower().startswith('strix-halo-lowbit-kernel-pack')
assert sorted(before)==sorted(row for row in after if keep(row))
assert version('strix-halo-lowbit-kernel-pack')=='0.1.0'
assert version('sglang')=='0.5.15'
assert version('sglang-kernel')=='0.4.4'
assert importlib.util.find_spec('sglang.srt.layers.quantization.gfx1151_lowbit') is not None
from hyperloom.inference_optimizer.rdna35_lowbit_hip import load_packaged_hip_module_manifest
module=load_packaged_hip_module_manifest()
assert module.sha256=='404cc2c0c49669cadb2be43326b7a3208c1e3e832ff77c6fd614238bbb9b0983'
assert module.qualification_sha256=='da7b2092176f108548e8d421c76026083da05d5b9df278837d3490af17f1a2e3'
print('HALOLOOM_SGLANG_FULL_RELEASE_STATIC_OK')
PY

LABEL haloloom.lowbit_overlay="strix-halo-lowbit-kernel-pack-0.1.0" \
      haloloom.lowbit_overlay_sha256="${LOWBIT_WHEEL_SHA256}" \
      haloloom.golden_compact_image_id="sha256:c14326489fcaf00aae97d53e805b2de44bf67f010b925801c86c2dd5cc00ade2" \
      haloloom.promotion_authority="false"
