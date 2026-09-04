# syntax=docker/dockerfile:1.7
ARG GOLDEN_IMAGE=hyperloom-vllm-v027-rocm10:v16-runtime-admission-v1
FROM ${GOLDEN_IMAGE} AS compacted

COPY scripts/prune_rocm10_gfx1151.py /opt/haloloom/prune_rocm10_gfx1151.py
COPY scripts/runtime_identity.py /opt/haloloom/runtime_identity.py
RUN /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-before.json \
      --package torch --package triton --package vllm --package hyperloom-inference_optimizer \
      --path vllm=/opt/venv/lib/python3.14/site-packages/vllm \
      --path hyperloom=/opt/venv/lib/python3.14/site-packages/hyperloom \
      --path bridge=/opt/hyperloom-runtime \
    && /opt/venv/bin/python3 /opt/haloloom/prune_rocm10_gfx1151.py \
      --runtime --manifest /opt/haloloom/prune-manifest.json \
    && /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/runtime-identity-after.json \
      --package torch --package triton --package vllm --package hyperloom-inference_optimizer \
      --path vllm=/opt/venv/lib/python3.14/site-packages/vllm \
      --path hyperloom=/opt/venv/lib/python3.14/site-packages/hyperloom \
      --path bridge=/opt/hyperloom-runtime \
    && cmp /opt/haloloom/runtime-identity-before.json /opt/haloloom/runtime-identity-after.json \
    && /opt/venv/bin/python3 -c 'import torch,vllm,hyperloom; assert not torch.cuda.is_available(); print("HALOLOOM_GOLDEN_VLLM_COMPACT_STATIC_OK")'

FROM scratch
COPY --from=compacted / /
ENV PATH=/opt/cargo/bin:/opt/venv/bin:/opt/rocm/bin:/opt/rocm/lib/llvm/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/venv \
    HYPERLOOM_ROOT=/opt/hyperloom \
    PYTHONPATH=/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/share/amd_smi:/opt/hyperloom-runtime \
    ROCM_PATH=/opt/rocm \
    HIP_PATH=/opt/rocm \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.14/site-packages/torch/lib:/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib:/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/rocm_sysdeps/lib:/opt/rocm/lib/host-math/lib:/opt/rocm/lib/llvm/lib:/opt/rocm/lib \
    HSA_ENABLE_SDMA=0 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RUSTUP_HOME=/opt/rustup \
    CARGO_HOME=/opt/cargo \
    VLLM_TARGET_DEVICE=rocm \
    PYTORCH_ROCM_ARCH=gfx1151 \
    HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1 \
    VLLM_GFX1151_LOWBIT_MANIFEST=/opt/venv/lib/python3.14/site-packages/hyperloom/inference_optimizer/assets/gfx1151/rdna35_lowbit/module-manifest.json \
    HYPERLOOM_ARCHIVE_PORT=w4a4-w8a8-source-faithful-v2 \
    HYPERLOOM_ARCHIVE_PORT_GPU_QUALIFIED=0 \
    HYPERLOOM_ARCHIVE_PORT_PROMOTION_AUTHORITY=0
LABEL org.opencontainers.image.title="HaloLoom vLLM full golden compact" \
      org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      haloloom.flavor="full" \
      haloloom.target="gfx1151" \
      haloloom.golden_image_id="sha256:0f2ef33105e11e60c11a3fce55a06860369329dcfc68d7627ad47f04a3c113ab" \
      haloloom.lowbit_pack="pinned-separate-source" \
      haloloom.promotion_authority="false"
ENTRYPOINT []
CMD ["/opt/venv/bin/python3", "-m", "vllm.entrypoints.openai.api_server", "--help"]
