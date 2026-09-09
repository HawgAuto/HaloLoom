# syntax=docker/dockerfile:1.7
ARG GOLDEN_IMAGE=haloloom-quark-golden-base-gfx1151:v0.1.0-rc1
FROM ${GOLDEN_IMAGE}

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/quark-runtime-src \
    USER_DATA_PATH=/workspace
# Keep MIOpen writes off HOME, which may be root-owned for a host UID.
ENV MIOPEN_CUSTOM_CACHE_DIR=/workspace/.cache/miopen \
    MIOPEN_USER_DB_PATH=/workspace/.cache/miopen_db

COPY scripts/runtime_identity.py /opt/haloloom/runtime_identity.py
COPY scripts/verify_quantization_contract.py /opt/haloloom/verify_quantization_contract.py
COPY dist/hyperloom/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl
COPY docker/quark/plugin-entrypoint /opt/haloloom/quark-entrypoint

RUN /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/golden-identity-before.json \
      --package torch --package amd-quark \
      --path quark=/opt/quark-runtime-src/quark \
      --path golden_hyperloom=/opt/hyperloom/src/hyperloom \
      --path quark_source=/opt/quark-source

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/haloloom-agent \
    && /opt/haloloom-agent/bin/pip install --upgrade pip setuptools wheel \
    && echo "c4e6ea5ec78fccbddddcff380842a14304e76d50b3c56369dd6025d65c502e7e  /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl" | sha256sum --check --strict \
    && /opt/haloloom-agent/bin/pip install \
       "/opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl[runtime]" \
    && agent_site="$(/opt/haloloom-agent/bin/python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
    && printf '%s\n' /opt/venv/lib/python3.12/site-packages > "$agent_site/quark-golden.pth" \
    && chmod 0755 /opt/haloloom/quark-entrypoint

RUN /opt/venv/bin/python3 /opt/haloloom/runtime_identity.py \
      --output /opt/haloloom/golden-identity-after.json \
      --package torch --package amd-quark \
      --path quark=/opt/quark-runtime-src/quark \
      --path golden_hyperloom=/opt/hyperloom/src/hyperloom \
      --path quark_source=/opt/quark-source \
    && cmp /opt/haloloom/golden-identity-before.json /opt/haloloom/golden-identity-after.json \
    && /opt/haloloom-agent/bin/python3 -c 'from importlib.metadata import version; import hyperloom,quark,torch; assert version("hyperloom-inference-optimizer")=="1.0.0"; assert version("amd-quark")=="0.12.post1"; assert torch.__version__=="2.13.0+rocm10.0.0"; assert hyperloom.__file__.startswith("/opt/haloloom-agent/"); assert quark.__file__.startswith("/opt/quark-runtime-src/")' \
    && /opt/haloloom-agent/bin/quantization-agent --help >/dev/null \
    && /opt/haloloom-agent/bin/python3 /opt/haloloom/verify_quantization_contract.py \
    && if ! getent passwd 1000 >/dev/null; then useradd --create-home --uid 1000 --shell /bin/bash haloloom; fi \
    && mkdir -p /workspace /home/haloloom/.hermes /home/haloloom/.codex /home/haloloom/.claude /opt/haloloom/agent-bin \
    && chown -R 1000:1000 /workspace /home/haloloom

ENV PATH=/opt/haloloom-agent/bin:/opt/haloloom/agent-bin:/usr/local/bin:/opt/venv/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/haloloom \
    VIRTUAL_ENV=/opt/haloloom-agent \
    HALOLOOM_AGENT_BIN_DIR=/opt/haloloom/agent-bin \
    ROCM_PATH=/opt/rocm/core-10.0 \
    ROCM_HOME=/opt/rocm/core-10.0 \
    HIP_PATH=/opt/rocm/core-10.0 \
    HIP_CLANG_PATH=/opt/rocm/core-10.0/lib/llvm/bin \
    HIP_DEVICE_LIB_PATH=/opt/rocm/core-10.0/amdgcn/bitcode \
    LD_LIBRARY_PATH=/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib \
    HSA_ENABLE_SDMA=0 \
    PYTORCH_ROCM_ARCH=gfx1151 \
    QUARK_ACCELERATOR=rocm \
    QUARK_ROOT=/opt/quark-source
LABEL org.opencontainers.image.title="HaloLoom Quark faithful agent" \
      org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      org.opencontainers.image.revision="eaca6d848babfe0bf969e7bc442bcffcec829e85" \
      haloloom.golden_base_image_id="sha256:ec7ded040c18e0a3bfc24c24bcddcd7b80c9149825616627d497cb496fbab418" \
      haloloom.hyperloom_wheel_sha256="c4e6ea5ec78fccbddddcff380842a14304e76d50b3c56369dd6025d65c502e7e" \
      haloloom.external_agent_clis_bundled="false" \
      haloloom.golden_runtime_unchanged="true" \
      haloloom.promotion_authority="false"
USER 1000:1000
WORKDIR /workspace
ENTRYPOINT ["/opt/haloloom/quark-entrypoint"]
CMD ["--help"]
