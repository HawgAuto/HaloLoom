# syntax=docker/dockerfile:1.7
# Build against one of the three GEAK source-bound local images. This is a
# transient build stage only; scripts/compact_codex_image.py publishes a fresh
# one-layer rootfs so the old CLI and old source archive cannot be recovered
# from inherited OCI layers.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS native-v2-applied
ARG PAYLOAD_SHA256
ARG GEAK_REF=cd1af9459f00d3d785978852c2b3399e90d72853
ARG HYPERLOOM_REF=942bf8e56e396cd1ad2592c9c61de970d6d1372a
USER root
COPY successor-build-inputs.tar.gz /opt/haloloom/native-v2-build-inputs.tar.gz
RUN set -eu; \
    echo "${PAYLOAD_SHA256}  /opt/haloloom/native-v2-build-inputs.tar.gz" | sha256sum -c -; \
    rm -rf /opt/haloloom/source-current /opt/haloloom/codex-amd; \
    mkdir -p /opt/haloloom/source-current; \
    tar -xzf /opt/haloloom/native-v2-build-inputs.tar.gz -C /opt/haloloom/source-current --no-same-owner; \
    rm /opt/haloloom/native-v2-build-inputs.tar.gz; \
    chown -R 1000:1000 /opt/haloloom/source-current; \
    /opt/venv/bin/python3 /opt/haloloom/source-current/apply-and-verify.py; \
    cp /opt/haloloom/source-current/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl; \
    cp /opt/haloloom/source-current/workbench-entrypoint /opt/haloloom/workbench-entrypoint; \
    chmod 0755 /opt/haloloom/workbench-entrypoint; \
    if [ -x /opt/haloloom-agent/bin/python3 ]; then \
      /opt/haloloom-agent/bin/python3 -m pip install --no-index --no-deps --force-reinstall \
        /opt/haloloom/source-current/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl; \
    fi; \
    /opt/haloloom/codex-amd/bin/codex --version | grep -Fx 'codex-cli 0.156.1'; \
    /opt/venv/bin/python3 /opt/haloloom/source-current/apply-and-verify.py --verify-only; \
    test ! -e /opt/haloloom/source-current/native-agent-source/codex-amd-source-rust-v0.153.4.tar.gz
COPY --from=haloloom_source docker/native-v2-successor/verify_ecosystem.py /opt/haloloom/verify_ecosystem.py
LABEL haloloom.promotion_authority="false" \
      haloloom.native_agent_source_ref="ad994060e04547932f4a88fe21115916e4262f81" \
      haloloom.geak_ref="${GEAK_REF}" \
      haloloom.hyperloom_ref="${HYPERLOOM_REF}" \
      haloloom.source_current="native-v2-source-bound-cpu-verified"
USER 1000:1000
RUN /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py
