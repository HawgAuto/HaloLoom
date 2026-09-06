# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=haloloom-vllm-full-gfx1151:v0.1.0-rc4
FROM ${BASE_IMAGE}

USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG HYPERLOOM_REF=eaca6d848babfe0bf969e7bc442bcffcec829e85
ARG MAGPIE_REF=25681df93ba21a1a6b0bdd4151884f42eead1063
ARG TRACELENS_REF=a59a9c165bb64c7c416fd7cf79149803d552e43c
ARG GEAK_REF=b4dea3fa33ef438d4233aae0ed2c2f425c4e419a
ARG INTELLIKIT_REF=2f61453a779980b00504ea3b772ff4a1a1c3f4ad
ARG INFERENCEX_REF=3d5581562f643f9bdeb8410cd924e2c70906c966
ARG VLLM_SOURCE_REF=6ddd7a77a256e90f86c108eeed4ce46602cf9657
ARG SGLANG_SOURCE_REF=cb9e016cb33b98bc804a57bc70b8272d8e8d134c

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ROCM_PATH=/opt/rocm/core-10.0 \
    ROCM_HOME=/opt/rocm/core-10.0 \
    HIP_PATH=/opt/rocm/core-10.0 \
    HIP_CLANG_PATH=/opt/rocm/core-10.0/lib/llvm/bin \
    HIP_DEVICE_LIB_PATH=/opt/rocm/core-10.0/amdgcn/bitcode \
    HSA_ENABLE_SDMA=0 \
    PYTORCH_ROCM_ARCH=gfx1151

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential ca-certificates cmake curl git jq libdwarf-dev libelf-dev \
       libhwloc-dev libnuma-dev libzstd-dev moreutils ninja-build nodejs npm patch \
       pkg-config python3-dev python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY patches/tracelens/python314-xprof-2.20.2.patch /opt/haloloom/patches/tracelens-python314-xprof.patch

RUN set -euo pipefail; \
    root=/opt/haloloom/components; mkdir -p "$root"; \
    fetch_exact() { \
      local name="$1" repo="$2" ref="$3"; \
      local attempt fetched=0; \
      for attempt in 1 2 3; do \
        rm -rf "$root/$name"; \
        git init -q "$root/$name"; \
        git -C "$root/$name" remote add origin "$repo"; \
        if timeout 300 git -C "$root/$name" \
          -c http.version=HTTP/1.1 -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=60 \
          fetch --depth 1 origin "$ref"; then \
          fetched=1; break; \
        fi; \
        echo "fetch_exact: $name attempt $attempt/3 failed; retrying from a fresh repository" >&2; \
        sleep $((attempt * 5)); \
      done; \
      test "$fetched" = 1; \
      git -C "$root/$name" checkout -q --detach FETCH_HEAD; \
      test "$(git -C "$root/$name" rev-parse HEAD)" = "$ref"; \
    }; \
    fetch_exact Hyperloom https://github.com/hstolte11-collab/Hyperloom.git "$HYPERLOOM_REF"; \
    fetch_exact Magpie https://github.com/HawgAuto/Magpie.git "$MAGPIE_REF"; \
    fetch_exact TraceLens https://github.com/AMD-AGI/TraceLens.git "$TRACELENS_REF"; \
    fetch_exact GEAK https://github.com/HawgAuto/GEAK.git "$GEAK_REF"; \
    fetch_exact IntelliKit https://github.com/AMDResearch/intellikit.git "$INTELLIKIT_REF"; \
    fetch_exact InferenceX https://github.com/SemiAnalysisAI/InferenceX.git "$INFERENCEX_REF"; \
    root=/opt/haloloom/framework-source; mkdir -p "$root"; \
    fetch_exact vllm https://github.com/HawgAuto/vllm.git "$VLLM_SOURCE_REF"; \
    fetch_exact sglang https://github.com/HawgAuto/sglang.git "$SGLANG_SOURCE_REF"; \
    echo "27483aa4507ff611ab4baac5258d0fe0b4811fedb359199d342794c4116f9b77  /opt/haloloom/patches/tracelens-python314-xprof.patch" | sha256sum --check --strict; \
    git -C /opt/haloloom/components/TraceLens apply --check /opt/haloloom/patches/tracelens-python314-xprof.patch; \
    git -C /opt/haloloom/components/TraceLens apply /opt/haloloom/patches/tracelens-python314-xprof.patch

COPY dist/hyperloom/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl
COPY scripts/verify_ecosystem.py /opt/haloloom/verify_ecosystem.py
COPY scripts/verify_quantization_contract.py /opt/haloloom/verify_quantization_contract.py
COPY scripts/magpie_patch_gate.py /opt/haloloom/magpie_patch_gate.py
COPY docker/ecosystem/workbench-entrypoint /opt/haloloom/workbench-entrypoint
COPY qualification/readiness /opt/haloloom/readiness

RUN set -euo pipefail; \
    wheel=/opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl; \
    lowbit=/opt/haloloom/wheels/strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl; \
    test -f "$lowbit"; \
    /opt/venv/bin/python3 -m pip check >/tmp/pip-check-before 2>&1 || true; \
    echo "c4e6ea5ec78fccbddddcff380842a14304e76d50b3c56369dd6025d65c502e7e  $wheel" | sha256sum --check --strict; \
    echo "e06d773292cb05c45fc61fffb251fcace49ef387c284c00208fb1827248ed8ad  $lowbit" | sha256sum --check --strict; \
    /opt/venv/bin/python3 -m pip install --no-index --no-deps --force-reinstall "$wheel"; \
    constraints=/tmp/haloloom-core-constraints.txt; : > "$constraints"; \
    for package in torch torchvision torchaudio triton grpcio protobuf; do \
      version=$(/opt/venv/bin/python3 -c "import importlib.metadata as m; print(m.version('$package'))" 2>/dev/null || true); \
      if [[ -n "$version" ]]; then printf '%s==%s\n' "$package" "$version" >> "$constraints"; fi; \
    done; \
    /opt/venv/bin/python3 -m pip install -c "$constraints" "$wheel[runtime,forge-profiling]" \
      'click>=8.4.2,<9' 'ray[default]==2.55.0' 'pandas>=2.2.3,<3' \
      'xprof==2.20.2' aiohttp datasets huggingface_hub lpips \
      msal openpyxl office365-rest-python-client orjson requests scikit-image tabulate transformers; \
    ROCM_PATH=/opt/rocm/core-10.0 \
      /opt/venv/bin/python3 -m pip install -e /opt/haloloom/components/IntelliKit/metrix; \
    /opt/venv/bin/python3 -m pip install --no-deps -e /opt/haloloom/components/Magpie; \
    /opt/venv/bin/python3 -m pip install --no-deps -e /opt/haloloom/components/TraceLens; \
    GEAK_SKIP_BOOTSTRAP=1 GEAK_HOME=/opt/haloloom/components/GEAK \
      /opt/venv/bin/python3 -m pip install -e /opt/haloloom/components/GEAK; \
    npm --prefix /opt/haloloom/components/GEAK/geak/workflow_runtime/node ci --ignore-scripts; \
    MAGPIE_PATH=/opt/haloloom/components/Magpie \
      INFERENCEX_PATH=/opt/haloloom/components/InferenceX \
      /opt/venv/bin/python3 /opt/haloloom/magpie_patch_gate.py /opt/haloloom/components/Magpie /opt/haloloom/components/InferenceX; \
    /opt/venv/bin/python3 -m pip install --no-index --no-deps --force-reinstall "$lowbit"; \
    /opt/venv/bin/python3 -m pip check >/tmp/pip-check-after 2>&1 || true; \
    /opt/venv/bin/python3 -c 'from pathlib import Path; before=set(Path("/tmp/pip-check-before").read_text().splitlines()); after=set(Path("/tmp/pip-check-after").read_text().splitlines()); new=sorted(after-before); assert not new,new; print("PIP_CHECK_NO_NEW_CONFLICTS",len(before),len(after))'; \
    /opt/venv/bin/python3 -c 'import ray; assert ray.__version__ == "2.55.0"'; \
    /opt/venv/bin/python3 -c 'import importlib.util as u; assert u.find_spec("hyperloom.inference_optimizer.rdna35_lowbit_adapter"); assert u.find_spec("hyperloom.inference_optimizer.rdna35_lowbit_hip")'; \
    chmod 0755 /opt/haloloom/workbench-entrypoint /opt/haloloom/verify_ecosystem.py; \
    /opt/venv/bin/inference_optimizer --help >/dev/null; \
    /opt/venv/bin/quantization-agent --help >/dev/null; \
    /opt/venv/bin/python3 /opt/haloloom/verify_quantization_contract.py; \
    /opt/venv/bin/kernelforge gemm-tune --help >/dev/null; \
    /opt/venv/bin/magpie --help >/dev/null; \
    /opt/venv/bin/metrix --help >/dev/null; \
    /opt/venv/bin/TraceLens_generate_perf_report_pytorch_inference --help >/dev/null; \
    test -f /opt/haloloom/components/GEAK/interface/run_e2e.py; \
    node --version; \
    if ! getent passwd 1000 >/dev/null; then useradd --create-home --uid 1000 --shell /bin/bash haloloom; fi; \
    mkdir -p /workspace /home/haloloom/.hermes /home/haloloom/.codex /home/haloloom/.claude; \
    chown -R 1000:1000 /workspace /home/haloloom /opt/haloloom/components /opt/haloloom/framework-source; \
    for repo in Hyperloom Magpie TraceLens GEAK IntelliKit InferenceX; do \
      git config --system --add safe.directory /opt/haloloom/components/$repo; \
    done; \
    for repo in vllm sglang; do \
      git config --system --add safe.directory /opt/haloloom/framework-source/$repo; \
    done; \
    /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py >/opt/haloloom/ecosystem-verification.json; \
    chown 1000:1000 /opt/haloloom/ecosystem-verification.json; \
    rm -rf /root/.cache/pip /tmp/haloloom-core-constraints.txt /tmp/pip-check-before /tmp/pip-check-after

ENV PATH=/opt/venv/bin:/opt/haloloom/agent-bin:/usr/local/bin:/opt/rocm/core-10.0/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/haloloom \
    RAY_VERSION=2.55.0 \
    RAY_CLI_CLICK_MAX_VERSION=9.0.0 \
    USER_DATA_PATH=/workspace \
    HYPERLOOM_RUNTIME_DIR=/workspace/runtime \
    KERNEL_AGENT_ENV=/workspace/runtime/kernel-agent.env.sh \
    HYPERLOOM_CACHE_DIR=/opt/haloloom/components \
    HYPERLOOM_DEPS_ROOT=/opt/haloloom/components \
    HYPERLOOM_ROOT=/opt/haloloom/components/Hyperloom \
    MAGPIE_PATH=/opt/haloloom/components/Magpie \
    MAGPIE_PYTHON=/opt/venv/bin/python3 \
    INFERENCEX_PATH=/opt/haloloom/components/InferenceX \
    TRACELENS_ROOT=/opt/haloloom/components/TraceLens \
    GEAK_ROOT=/opt/haloloom/components/GEAK \
    GEAK_E2E_RUNNER=/opt/haloloom/components/GEAK/interface/run_e2e.py \
    INFERENCE_OPTIMIZER_FRAMEWORK_SOURCE_ROOTS=/opt/haloloom/framework-source/vllm:/opt/haloloom/framework-source/sglang \
    HALOLOOM_AGENT_BIN_DIR=/opt/haloloom/agent-bin

LABEL org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      haloloom.ecosystem_complete="true" \
      haloloom.hyperloom_ref="eaca6d848babfe0bf969e7bc442bcffcec829e85" \
      haloloom.magpie_ref="25681df93ba21a1a6b0bdd4151884f42eead1063" \
      haloloom.tracelens_ref="a59a9c165bb64c7c416fd7cf79149803d552e43c" \
      haloloom.geak_ref="b4dea3fa33ef438d4233aae0ed2c2f425c4e419a" \
      haloloom.intellikit_ref="2f61453a779980b00504ea3b772ff4a1a1c3f4ad" \
      haloloom.inferencex_ref="3d5581562f643f9bdeb8410cd924e2c70906c966" \
      haloloom.vllm_source_ref="6ddd7a77a256e90f86c108eeed4ce46602cf9657" \
      haloloom.sglang_source_ref="cb9e016cb33b98bc804a57bc70b8272d8e8d134c" \
      haloloom.external_agent_clis_bundled="false" \
      haloloom.promotion_authority="false"
