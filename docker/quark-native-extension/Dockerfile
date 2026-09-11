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
LABEL org.opencontainers.image.source="https://github.com/HawgAuto/HaloLoom" \
      haloloom.quark_extension="precompiled-native-gfx1151"
USER 1000:1000
RUN LD_LIBRARY_PATH=/opt/quark-venv/lib/python3.12/site-packages/torch/lib:/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib \
    PYTHONDONTWRITEBYTECODE=1 QUARK_BUILD_DISABLE_JIT_FALLBACK=1 \
    /opt/quark-venv/bin/python -c 'import os,torch,quark.torch; assert os.geteuid()==1000; assert any(n.startswith("quark_hw_emulation::") for n in torch._C._dispatch_get_all_op_names()); print("QUARK_NONROOT_PRECOMPILED_IMPORT_OK")'
