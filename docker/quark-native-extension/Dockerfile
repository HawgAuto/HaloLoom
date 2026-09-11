# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=ghcr.io/hawgauto/haloloom-quark-rocm10-gfx1151@sha256:8c7553658267495a0d2b4d0279c9d23f9a71a50297947d1d0fd40a18547f7942
FROM ${BASE_IMAGE} AS extension-build
USER root
COPY scripts/package_quark_native_extension.py /opt/haloloom/package_quark_native_extension.py
# Quark uses Python 3.12; serving uses Python 3.14. Select libraries per process,
# never change the serving interpreter's image-wide library path.
RUN LD_LIBRARY_PATH=/opt/quark-venv/lib/python3.12/site-packages/torch/lib:/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib \
    PYTHONDONTWRITEBYTECODE=1 PYTORCH_ROCM_ARCH=gfx1151 MAX_JOBS=4 \
    /opt/quark-venv/bin/python /opt/haloloom/package_quark_native_extension.py --output /quark-extension-payload

FROM ${BASE_IMAGE}
COPY --from=extension-build /quark-extension-payload/ /
USER root
COPY patches/vllm/quark-excluded-embedding.patch /opt/haloloom/quark-excluded-embedding.patch
# Apply only to the exact installed source; never silently patch a different ABI.
RUN set -eu; \
    target=/opt/venv/lib/python3.14/site-packages/vllm/model_executor/layers/quantization/quark/quark.py; \
    if printf 'b93e25d93466adde5e9d7725199d9d2fd9c57a9cf9eb6418ecf434ab5c28784c  %s\n' "$target" | sha256sum --check --status; then :; else \
      printf '80099b0b5874264ea51d17422cfcf50633f8698f8bd8e50b4aeef4eb02d5408e  %s\n' "$target" | sha256sum --check --strict; \
      cd /opt/venv/lib/python3.14/site-packages; \
      git apply --check /opt/haloloom/quark-excluded-embedding.patch; \
      git apply /opt/haloloom/quark-excluded-embedding.patch; \
    fi; \
    printf 'b93e25d93466adde5e9d7725199d9d2fd9c57a9cf9eb6418ecf434ab5c28784c  %s\n' "$target" | sha256sum --check --strict
COPY tests/image/quark_excluded_embeddings.py /opt/haloloom/image-tests/quark_excluded_embeddings.py
LABEL org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      haloloom.quark_extension="precompiled-native-gfx1151" \
      haloloom.quark_embedding_adapter="native-unquantized-embedding"
USER 1000:1000
RUN LD_LIBRARY_PATH=/opt/quark-venv/lib/python3.12/site-packages/torch/lib:/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib \
    PYTHONDONTWRITEBYTECODE=1 QUARK_BUILD_DISABLE_JIT_FALLBACK=1 \
    /opt/quark-venv/bin/python -c 'import os,torch,quark.torch; assert os.geteuid()==1000; assert any(n.startswith("quark_hw_emulation::") for n in torch._C._dispatch_get_all_op_names()); print("QUARK_NONROOT_PRECOMPILED_IMPORT_OK")'
RUN PYTHONDONTWRITEBYTECODE=1 VLLM_CACHE_ROOT=/tmp/vllm /opt/venv/bin/python3 -m pytest \
    /opt/haloloom/image-tests/quark_excluded_embeddings.py \
    --confcutdir /opt/haloloom/image-tests -q -p no:cacheprovider
