# syntax=docker/dockerfile:1.7
ARG GOLDEN_IMAGE=hyperloom-sglang-v0515-rocm10:v16-async-v7
FROM ${GOLDEN_IMAGE} AS compacted

COPY scripts/prune_rocm10_gfx1151.py /opt/haloloom/prune_rocm10_gfx1151.py
COPY scripts/runtime_identity.py /opt/haloloom/runtime_identity.py
RUN /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-before.json \
      --package torch --package triton --package sglang --package sglang-kernel --package hyperloom-inference_optimizer \
      --path sglang=/opt/venv/lib/python3.14/site-packages/sglang \
      --path sgl_kernel=/opt/venv/lib/python3.14/site-packages/sgl_kernel \
      --path hyperloom=/opt/venv/lib/python3.14/site-packages/hyperloom \
      --path bridge=/opt/hyperloom-runtime \
    && /opt/venv/bin/python3 /opt/haloloom/prune_rocm10_gfx1151.py \
      --runtime --manifest /opt/haloloom/prune-manifest.json \
    && /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-after.json \
      --package torch --package triton --package sglang --package sglang-kernel --package hyperloom-inference_optimizer \
      --path sglang=/opt/venv/lib/python3.14/site-packages/sglang \
      --path sgl_kernel=/opt/venv/lib/python3.14/site-packages/sgl_kernel \
      --path hyperloom=/opt/venv/lib/python3.14/site-packages/hyperloom \
      --path bridge=/opt/hyperloom-runtime \
    && cmp /opt/haloloom/runtime-identity-before.json /opt/haloloom/runtime-identity-after.json \
    && /opt/venv/bin/python3 -c 'import torch,sglang,hyperloom; assert not torch.cuda.is_available(); print("HALOLOOM_GOLDEN_SGLANG_COMPACT_STATIC_OK")'

FROM scratch
COPY --from=compacted / /
ENV PATH=/opt/cargo/bin:/opt/venv/bin:/opt/rocm/bin:/opt/rocm/lib/llvm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/venv \
    HYPERLOOM_ROOT=/opt/hyperloom \
    PYTHONPATH=/opt/hyperloom-runtime \
    ROCM_PATH=/opt/rocm \
    HIP_PATH=/opt/rocm \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.14/site-packages/torch/lib:/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib:/opt/rocm/lib/host-math/lib:/opt/rocm/lib/llvm/lib:/opt/rocm/lib \
    HSA_ENABLE_SDMA=0 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUSTUP_HOME=/opt/rustup \
    CARGO_HOME=/opt/cargo \
    PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 \
    PYTORCH_ROCM_ARCH=gfx1151 \
    SGLANG_USE_AITER=0 \
    HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1 \
    SGLANG_GFX1151_LOWBIT_MANIFEST=/opt/venv/lib/python3.14/site-packages/hyperloom/inference_optimizer/assets/gfx1151/rdna35_lowbit/module-manifest.json \
    HYPERLOOM_RUNTIME_EPOCH=async-v7 \
    HYPERLOOM_RUNTIME_COMPLETION=hip-event-request-step
LABEL org.opencontainers.image.title="HaloLoom SGLang full golden compact" \
      org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      haloloom.flavor="full" \
      haloloom.target="gfx1151" \
      haloloom.golden_image_id="sha256:869e23eec020047c4dc57f6ee42fd33107ea53f0ec202f9fd2b1d795235c7e50" \
      haloloom.lowbit_pack="pinned-separate-source" \
      haloloom.promotion_authority="false"
ENTRYPOINT []
CMD ["/opt/venv/bin/python3", "-m", "sglang.launch_server", "--help"]
