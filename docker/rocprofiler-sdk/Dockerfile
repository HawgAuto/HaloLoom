ARG BASE_IMAGE
FROM ${BASE_IMAGE}
# Explicit local repair layer: no package installation or framework writes.
USER root
COPY --chown=0:0 dist/rocprofiler-sdk/candidate.so /opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocprofiler-sdk.so.1
COPY --chown=0:0 dist/rocprofiler-sdk/candidate.so /opt/rocm/core-10.0/lib/librocprofiler-sdk.so.1.3.5
COPY --chown=0:0 profiling/rocprofiler-sdk/ /opt/haloloom/profiling/rocprofiler-sdk/
COPY --chown=0:0 manifests/rocprofiler-sdk-repair.json /opt/haloloom/profiling/rocprofiler-sdk/rocprofiler-sdk-repair.json
RUN /opt/venv/bin/python -B /opt/haloloom/profiling/rocprofiler-sdk/verify_runtime.py
LABEL haloloom.profiling.sdk_accounting="mixed-aql-balanced-v1" \
      haloloom.profiling.clock="rocprofiler_get_timestamp-CLOCK_BOOTTIME" \
      haloloom.profiling.scope="on-demand-metrix-only" \
      haloloom.optimizer_resume_authorized="false"
USER 1000:1000
