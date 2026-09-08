ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS source-current
# Optional custom routes are enabled explicitly by scripts/serve.py.
ENV HYPERLOOM_GFX1151_LOWBIT_BRIDGE=0
USER root
COPY --chown=1000:1000 dist/source-current/ /opt/haloloom/source-current/
RUN /opt/venv/bin/python3 /opt/haloloom/source-current/apply-and-verify.py
# Keep native evaluation tasks compatible with namespace-qualified HF URIs.
COPY dist/source-current/qualify_eval_task_namespaces.py /opt/haloloom/qualify_eval_task_namespaces.py
RUN /opt/venv/bin/python3 /opt/haloloom/qualify_eval_task_namespaces.py --report /opt/haloloom/lm-eval-task-namespaces.json
# The bundled Quark agent has a separate supported Python runtime.
# Update its Hyperloom wheel too; leave its Quark/Torch runtime untouched.
RUN if [ -x /opt/haloloom-agent/bin/python3 ]; then \
      /opt/haloloom-agent/bin/python3 -m pip install --no-index --no-deps --force-reinstall \
        /opt/haloloom/source-current/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl && \
      /opt/haloloom-agent/bin/python3 -c 'import importlib.metadata as m,zipfile,sysconfig,pathlib; d=m.distribution("hyperloom-inference-optimizer"); z=zipfile.ZipFile("/opt/haloloom/source-current/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl"); names=[n for n in z.namelist() if ".dist-info/" not in n and not n.endswith("/")]; assert names and all((pathlib.Path(sysconfig.get_path("data"))/n.split(".data/data/",1)[1] if ".data/data/" in n else d.locate_file(n)).read_bytes()==z.read(n) for n in names); print("QUARK_AGENT_WHEEL_PAYLOAD_MATCH",len(names))'; \
    fi
# Native TraceLens git-apply needs writable directory entries at runtime.
# Change directories only, never the native library bytes or server source.
RUN /opt/venv/bin/python3 -c 'import os,importlib.metadata as m; installed={d.metadata["Name"].lower().replace("_","-"):d for d in m.distributions()}; roots=[installed[name].locate_file(name) for name in ("vllm","sglang") if name in installed]; [os.chown(directory,1000,1000) for root in roots for directory,_,_ in os.walk(root)]'
COPY dist/source-current/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl /opt/haloloom/wheels/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl
COPY dist/source-current/verify_ecosystem.py /opt/haloloom/verify_ecosystem.py
# The source-bound archive carries the current CLI-selection entrypoint too.
COPY --chmod=0755 dist/source-current/workbench-entrypoint /opt/haloloom/workbench-entrypoint
LABEL haloloom.hyperloom_ref="b91cab3433002fa8381108dd5ea7cb3633b6955e" \
      haloloom.vllm_source_ref="861cd9d993a7c92728db6d73cb0b62fa0df7c8a0" \
      haloloom.sglang_source_ref="90c62e027831111934a33b9bcc4e533ff61d8526" \
      haloloom.source_current="verified-offline-git-and-installed-python" \
      haloloom.promotion_authority="false"
USER 1000:1000
RUN /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py

FROM source-current AS vllm
ENV ROCP_TOOL_LIBRARIES=/opt/venv/lib/python3.14/site-packages/torch/lib/libtorch_cpu.so \
    LD_LIBRARY_PATH=/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/host-math/lib:/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib

FROM source-current AS sglang
# Match Compose's existing cache root for non-root direct image use.
ENV SGLANG_CACHE_DIR=/workspace/.cache/sglang
USER root
COPY --chown=1000:1000 dist/source-current/tracelens-sglang-0519/ /opt/haloloom/tracelens-sglang-0519/
RUN /opt/venv/bin/python3 /opt/haloloom/tracelens-sglang-0519/apply-reviewed-patch.py
LABEL haloloom.tracelens_sglang_patch_sha256="a2280f784472ec202010541b86b20de19837b8582bf5bbc151718aaefabb0b86"
USER 1000:1000
RUN /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py

FROM source-current AS quark
