# syntax=docker/dockerfile:1.7
ARG DEVEL_IMAGE=docker.io/rocm/dev-ubuntu-26.04:10.0.0-full@sha256:8ebc02ee1aefb6b7c0e952b4088542133bad8805d19730db92cc61be673421d1
ARG BASE_IMAGE=docker.io/rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0@sha256:3174cb7061d94c427da96c0edef4adea28046fa3f3b2ff3948dc4e995665ff8c
FROM ${DEVEL_IMAGE} AS devel
FROM ${BASE_IMAGE} AS assembled

USER root
COPY --from=devel /opt/rocm /opt/rocm
RUN set -eux; \
    rm -f /opt/rocm/amdgcn /opt/rocm/bin /opt/rocm/core /opt/rocm/core-10 \
          /opt/rocm/include /opt/rocm/lib /opt/rocm/libexec /opt/rocm/llvm /opt/rocm/share; \
    ln -s core-10.0/lib/llvm/amdgcn /opt/rocm/amdgcn; \
    ln -s core-10.0/bin /opt/rocm/bin; \
    ln -s core-10.0 /opt/rocm/core; \
    ln -s core-10.0 /opt/rocm/core-10; \
    ln -s core-10.0/include /opt/rocm/include; \
    ln -s core-10.0/lib /opt/rocm/lib; \
    ln -s core-10.0/libexec /opt/rocm/libexec; \
    ln -s core-10.0/lib/llvm /opt/rocm/llvm; \
    ln -s core-10.0/share /opt/rocm/share; \
    runtime_hip="$(/opt/venv/bin/python3 -c 'import pathlib,torch; print(next(pathlib.Path(torch.__file__).resolve().parent.parent.glob("_rocm_sdk_core/lib/libamdhip64.so.7")))')"; \
    rm -f /opt/rocm/lib/libamdhip64.so /opt/rocm/lib/libamdhip64.so.7; \
    ln -s "$runtime_hip" /opt/rocm/lib/libamdhip64.so.7; \
    ln -s "$runtime_hip" /opt/rocm/lib/libamdhip64.so

COPY dist/hyperloom/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl
COPY scripts/prune_rocm10_gfx1151.py /opt/haloloom/prune_rocm10_gfx1151.py
RUN echo "212f721a610943b671ae40ed2356213add4ea9dd7a2c40adc7d1caacfc727e93  /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl" | sha256sum --check --strict \
    && /opt/venv/bin/python3 -m pip install --no-index --no-deps --force-reinstall \
       /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl \
    && /opt/venv/bin/python3 /opt/haloloom/prune_rocm10_gfx1151.py \
       --runtime --manifest /opt/haloloom/prune-manifest.json \
    && /opt/venv/bin/python3 /opt/haloloom/prune_rocm10_gfx1151.py \
       --dry-run --runtime --manifest /opt/haloloom/post-prune-audit.json \
    && /opt/venv/bin/python3 - <<'PY'
import json
from importlib.metadata import version
from pathlib import Path
import torch
post = json.loads(Path('/opt/haloloom/post-prune-audit.json').read_text())
assert post['removed_entry_count'] == 0, post['removed_entries'][:10]
assert torch.__version__ == '2.13.0+rocm10.0.0'
assert torch.version.hip == '7.15.26333'
assert version('rocm') == '10.0.0'
assert version('hyperloom-inference_optimizer') == '1.0.0'
assert not torch.cuda.is_available()
print('HALOLOOM_PUBLIC_SLIM_BASE_STATIC_OK')
PY
RUN test ! -e /dev/kfd \
    && test ! -e /dev/dri \
    && test -x /opt/rocm/bin/hipcc \
    && test -x /opt/rocm/lib/llvm/bin/llvm-objdump \
    && /opt/venv/bin/hyperloom --help >/dev/null

FROM scratch
COPY --from=assembled / /
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/venv \
    ROCM_PATH=/opt/rocm \
    ROCM_HOME=/opt/rocm \
    HIP_PATH=/opt/rocm \
    HIP_CLANG_PATH=/opt/rocm/lib/llvm/bin \
    HIP_DEVICE_LIB_PATH=/opt/rocm/amdgcn/bitcode \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib:/opt/rocm/lib/llvm/lib:/opt/rocm/lib \
    HSA_ENABLE_SDMA=0 \
    PYTORCH_ROCM_ARCH=gfx1151
LABEL org.opencontainers.image.title="HaloLoom ROCm 10 gfx1151 slim base" \
      org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      org.opencontainers.image.revision="eaca6d848babfe0bf969e7bc442bcffcec829e85" \
      haloloom.target="gfx1151" \
      haloloom.hyperloom_wheel_sha256="212f721a610943b671ae40ed2356213add4ea9dd7a2c40adc7d1caacfc727e93" \
      haloloom.promotion_authority="false"
ENTRYPOINT []
CMD ["/opt/venv/bin/python3", "-c", "import torch; print(torch.__version__, torch.version.hip)"]
