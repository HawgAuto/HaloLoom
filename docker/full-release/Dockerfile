# syntax=docker/dockerfile:1.7
# Apply a complete, exact source/wheel packet to a qualified matching runtime.
# BASE_IMAGE must be independently bound to the intended ABI and variant.
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS full-release-applied
ARG PAYLOAD_SHA256
ARG VARIANT
USER root
COPY full-release-inputs.tar.gz /opt/haloloom/full-release-inputs.tar.gz
COPY plugin-entrypoint /opt/haloloom/quark-entrypoint
RUN set -eu; \
    test -n "${PAYLOAD_SHA256}"; \
    chmod 0755 /opt/haloloom/quark-entrypoint; \
    test "${VARIANT}" = vllm -o "${VARIANT}" = sglang -o "${VARIANT}" = quark; \
    echo "${PAYLOAD_SHA256}  /opt/haloloom/full-release-inputs.tar.gz" | sha256sum -c -; \
    rm -rf /opt/haloloom/source-current; \
    mkdir -p /opt/haloloom/source-current /workspace; \
    tar -xzf /opt/haloloom/full-release-inputs.tar.gz -C /opt/haloloom/source-current --no-same-owner; \
    rm /opt/haloloom/full-release-inputs.tar.gz; \
    /opt/venv/bin/python /opt/haloloom/source-current/apply_and_verify.py --variant "${VARIANT}"; \
    cp /opt/haloloom/source-current/verify_ecosystem.py /opt/haloloom/verify_ecosystem.py; \
    install -m 0755 /opt/haloloom/source-current/release-entrypoint /opt/haloloom/release-entrypoint; \
    cp -a /opt/haloloom/source-current/sdk/profiling /opt/haloloom/profiling-full-release; \
    chown -R 1000:1000 /opt/haloloom/source-current /workspace
ENV HALOLOOM_RELEASE_VARIANT=${VARIANT} \
    HYPERLOOM_VLLM_TRACELENS_MANIFEST=/opt/haloloom/vllm-tracelens-install.json
ENTRYPOINT ["/opt/haloloom/release-entrypoint"]
LABEL haloloom.promotion_authority="false" \
      haloloom.release="v0.1.4" \
      haloloom.source_current="complete-accepted-repair-integration" \
      haloloom.full_release_payload_sha256="${PAYLOAD_SHA256}"
USER 1000:1000
WORKDIR /workspace
RUN /opt/venv/bin/python /opt/haloloom/verify_ecosystem.py
