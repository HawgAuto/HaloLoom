#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
out="$here/build"
mkdir -p "$out"
ROCM=/opt/rocm/core-10.0
"$ROCM/bin/hipcc" --genco --offload-arch=gfx1151 -O2 "$here/vector_add.hip" -o "$out/vector_add.bundle"
"$ROCM/lib/llvm/bin/clang-offload-bundler" -unbundle -type=o \
  -targets=hipv4-amdgcn-amd-amdhsa--gfx1151 \
  -input="$out/vector_add.bundle" -output="$out/vector_add_gfx1151.hsaco"
"$ROCM/lib/llvm/bin/clang++" -std=c++17 -O2 -Wall -Wextra -Werror \
  -I"$ROCM/include" "$here/mixed_aql_fixture.cpp" \
  -L"$ROCM/lib" -Wl,-rpath,"$ROCM/lib" -lhsa-runtime64 \
  -o "$out/mixed_aql_fixture"
sha256sum "$here/vector_add.hip" "$here/mixed_aql_fixture.cpp" \
  "$out/vector_add_gfx1151.hsaco" "$out/mixed_aql_fixture" > "$out/SHA256SUMS"
"$ROCM/lib/llvm/bin/llvm-readelf" -h -n "$out/vector_add_gfx1151.hsaco" > "$out/code-object-readelf.txt"
printf 'BUILD_OK %s\n' "$out"
