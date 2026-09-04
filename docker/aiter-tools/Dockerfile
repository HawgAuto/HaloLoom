# syntax=docker/dockerfile:1.7
ARG GOLDEN_IMAGE=hyperloom-sglang-v0515-rocm10:aiter-gfx1151-current-main-v3
FROM ${GOLDEN_IMAGE} AS compacted

COPY scripts/prune_rocm10_gfx1151.py /opt/haloloom/prune_rocm10_gfx1151.py
COPY scripts/runtime_identity.py /opt/haloloom/runtime_identity.py
RUN /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-before.json \
      --package torch --package triton --package sglang --package sglang-kernel \
      --package amd-aiter --package hyperloom-inference_optimizer \
      --path sglang=/opt/venv/lib/python3.14/site-packages/sglang \
      --path sgl_kernel=/opt/venv/lib/python3.14/site-packages/sgl_kernel \
      --path hyperloom=/opt/venv/lib/python3.14/site-packages/hyperloom \
      --path bridge=/opt/hyperloom-runtime \
    && /opt/venv/bin/python3 /opt/haloloom/prune_rocm10_gfx1151.py \
      --runtime --manifest /opt/haloloom/prune-manifest.json \
    && /opt/venv/bin/python3 /opt/haloloom/prune_rocm10_gfx1151.py \
      --dry-run --runtime --manifest /opt/haloloom/post-prune-audit.json \
    && /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-after.json \
      --package torch --package triton --package sglang --package sglang-kernel \
      --package amd-aiter --package hyperloom-inference_optimizer \
      --path sglang=/opt/venv/lib/python3.14/site-packages/sglang \
      --path sgl_kernel=/opt/venv/lib/python3.14/site-packages/sgl_kernel \
      --path hyperloom=/opt/venv/lib/python3.14/site-packages/hyperloom \
      --path bridge=/opt/hyperloom-runtime \
    && cmp /opt/haloloom/runtime-identity-before.json /opt/haloloom/runtime-identity-after.json \
    && /opt/venv/bin/python3 - <<'PY'
from importlib.metadata import version
from importlib.util import find_spec
from pathlib import Path
import json
import torch
post = json.loads(Path('/opt/haloloom/post-prune-audit.json').read_text())
assert post['removed_entry_count'] == 0
assert version('amd-aiter') == '0.1.22.dev0+gfx1151.rocm10'
assert torch.__version__ == '2.13.0+rocm10.0.0'
assert not torch.cuda.is_available()
spec = find_spec('aiter')
assert spec is not None and spec.origin is not None and Path(spec.origin).is_file()
print('HALOLOOM_GOLDEN_AITER_COMPACT_STATIC_OK')
PY

FROM scratch
COPY --from=compacted / /
ENV PATH=/opt/cargo/bin:/opt/venv/bin:/opt/rocm/bin:/opt/rocm/lib/llvm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/venv \
    HYPERLOOM_ROOT=/opt/hyperloom \
    PYTHONPATH=/opt/hyperloom-runtime \
    ROCM_PATH=/opt/rocm/core-10.0 \
    ROCM_HOME=/opt/rocm/core-10.0 \
    HIP_PATH=/opt/rocm/core-10.0 \
    LD_LIBRARY_PATH=/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib \
    HSA_ENABLE_SDMA=0 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUSTUP_HOME=/opt/rustup \
    CARGO_HOME=/opt/cargo \
    PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 \
    PYTORCH_ROCM_ARCH=gfx1151 \
    SGLANG_USE_AITER=1 \
    HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1 \
    SGLANG_GFX1151_LOWBIT_MANIFEST=/opt/venv/lib/python3.14/site-packages/hyperloom/inference_optimizer/assets/gfx1151/rdna35_lowbit/module-manifest.json \
    HYPERLOOM_RUNTIME_EPOCH=async-v7 \
    HYPERLOOM_RUNTIME_COMPLETION=hip-event-request-step \
    AITER_ROCM_ARCH=gfx1151 \
    GPU_ARCHS=gfx1151
LABEL org.opencontainers.image.title="HaloLoom AITER tools golden compact" \
      org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      haloloom.golden_image_id="sha256:e9647f36b4659b3272c1689fcbb85fee17002a7ead9516c09f3e310ec9e719e6" \
      haloloom.aiter_attention_qualified="false" \
      haloloom.supported_sglang_attention="triton" \
      haloloom.promotion_authority="false"
ENTRYPOINT []
CMD ["/opt/venv/bin/python3", "-m", "sglang.launch_server", "--help"]
