# syntax=docker/dockerfile:1.7
ARG GOLDEN_IMAGE=hyperloom-quark-rocm10:gfx1151-v4
FROM ${GOLDEN_IMAGE} AS compacted

COPY scripts/prune_rocm10_gfx1151.py /opt/haloloom/prune_rocm10_gfx1151.py
COPY scripts/runtime_identity.py /opt/haloloom/runtime_identity.py
RUN /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-before.json \
      --package torch --package amd-quark --package hyperloom-inference_optimizer \
      --path quark=/opt/quark-runtime-src/quark \
      --path hyperloom=/opt/hyperloom/src/hyperloom \
      --path quark_source=/opt/quark-source \
    && /opt/venv/bin/python3 /opt/haloloom/prune_rocm10_gfx1151.py \
      --runtime --manifest /opt/haloloom/prune-manifest.json \
    && /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-after.json \
      --package torch --package amd-quark --package hyperloom-inference_optimizer \
      --path quark=/opt/quark-runtime-src/quark \
      --path hyperloom=/opt/hyperloom/src/hyperloom \
      --path quark_source=/opt/quark-source \
    && cmp /opt/haloloom/runtime-identity-before.json /opt/haloloom/runtime-identity-after.json \
    && /opt/venv/bin/python3 -c 'import torch,quark,hyperloom; assert not torch.cuda.is_available(); from quark.torch import LLMTemplate; assert "qwen3" in LLMTemplate.list_available(); print("HALOLOOM_GOLDEN_QUARK_COMPACT_STATIC_OK")'

FROM scratch
COPY --from=compacted / /
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/venv \
    PYTHONPATH=/opt/hyperloom/src:/opt/quark-runtime-src \
    ROCM_PATH=/opt/rocm \
    ROCM_HOME=/opt/rocm \
    HIP_PATH=/opt/rocm \
    HIP_CLANG_PATH=/opt/rocm/lib/llvm/bin \
    HIP_DEVICE_LIB_PATH=/opt/rocm/amdgcn/bitcode \
    HSA_ENABLE_SDMA=0 \
    QUARK_ACCELERATOR=rocm \
    QUARK_ROOT=/opt/quark-source \
    PIP_DISABLE_PIP_VERSION_CHECK=1
LABEL org.opencontainers.image.title="HaloLoom Quark golden compact base" \
      org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      haloloom.flavor="golden-base" \
      haloloom.target="gfx1151" \
      haloloom.golden_image_id="sha256:4e01a1bb36eb72eea6e5c36da43901cb0bab56b8d32e3ab61a369ef66dca6774" \
      haloloom.promotion_authority="false"
USER root
ENTRYPOINT ["/opt/venv/bin/python3", "-m", "hyperloom.agents.quantization.gfx1151_worker"]
