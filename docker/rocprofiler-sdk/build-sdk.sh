#!/usr/bin/env bash
set -euo pipefail
# CPU-only build: no device mounts and no runtime feature suppression.
export PKG_CONFIG_PATH=/opt/rocm/core-10.0/lib/rocm_sysdeps/lib/pkgconfig
export LD_LIBRARY_PATH=/opt/rocm/core-10.0/lib/rocm_sysdeps/lib:/opt/rocm/core-10.0/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export LIBRARY_PATH=/opt/rocm/core-10.0/lib/rocm_sysdeps/lib${LIBRARY_PATH:+:$LIBRARY_PATH}
cmake -S /work/source/projects/rocprofiler-sdk -B /work/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=/opt/rocm/core-10.0 \
  -DCMAKE_MODULE_PATH=/work/cmake-modules \
  -DCMAKE_INSTALL_PREFIX=/opt/rocm/core-10.0 -DGPU_TARGETS=gfx1151 \
  -DCMAKE_BUILD_RPATH='/opt/rocm/core-10.0/lib/rocm_sysdeps/lib;/opt/rocm/core-10.0/lib' \
  '-DFETCHCONTENT_SOURCE_DIR_OTF2-SOURCE=/work/deps/otf2-source' \
  2>&1 | tee /work/configure.log
cmake --build /work/build --target rocprofiler-sdk-shared-library --parallel 8 2>&1 | tee /work/build.log

# Build the pinned packaging tool inside the CPU-only capsule; no host install.
(
  cd /work/deps/patchelf-source
  ./configure --quiet
  make --quiet -j8
)
# Match the qualified vendor loader policy, not CMake's build RUNPATH.
mkdir -p /work/artifacts
cp /work/build/lib/librocprofiler-sdk.so.1.3.5 /work/artifacts/candidate.so
/work/deps/patchelf-source/src/patchelf --force-rpath --set-rpath '$ORIGIN/rocm_sysdeps/lib:$ORIGIN/llvm/lib:$ORIGIN:$ORIGIN/../../_rocm_sdk_core/lib/llvm/lib:$ORIGIN/../../_rocm_sdk_core/lib/rocm_sysdeps/lib' /work/artifacts/candidate.so
sha256sum /work/artifacts/candidate.so
