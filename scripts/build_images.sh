#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
unset HSA_OVERRIDE_GFX_VERSION
VERSION=${HALOLOOM_VERSION:-v0.1.0}

shopt -s nullglob
lowbit_wheels=(dist/lowbit/strix_halo_lowbit_kernel_pack-*.whl)
vllm_wheels=(dist/frameworks/vllm-full-composite/vllm-*.whl)
[[ ${#lowbit_wheels[@]} == 1 && -f ${lowbit_wheels[0]} ]]
[[ ${#vllm_wheels[@]} == 1 && -f ${vllm_wheels[0]} ]]
LOWBIT_WHEEL_SHA256=$(sha256sum "${lowbit_wheels[0]}")
LOWBIT_WHEEL_SHA256=${LOWBIT_WHEEL_SHA256%% *}
VLLM_WHEEL_SHA256=$(sha256sum "${vllm_wheels[0]}")
VLLM_WHEEL_SHA256=${VLLM_WHEEL_SHA256%% *}

require_image_id() {
  local reference=$1
  local expected=$2
  local actual
  actual=$(docker image inspect --format '{{.Id}}' "$reference")
  if [[ "$actual" != "$expected" ]]; then
    printf 'ERROR: image identity mismatch: %s expected=%s actual=%s\n' \
      "$reference" "$expected" "$actual" >&2
    return 1
  fi
}

require_image_id \
  hyperloom-vllm-v027-rocm10:v16-runtime-admission-v1 \
  sha256:0f2ef33105e11e60c11a3fce55a06860369329dcfc68d7627ad47f04a3c113ab
require_image_id \
  hyperloom-sglang-v0515-rocm10:v16-async-v7 \
  sha256:869e23eec020047c4dc57f6ee42fd33107ea53f0ec202f9fd2b1d795235c7e50
require_image_id \
  hyperloom-quark-rocm10:gfx1151-v4 \
  sha256:4e01a1bb36eb72eea6e5c36da43901cb0bab56b8d32e3ab61a369ef66dca6774
require_image_id \
  hyperloom-sglang-v0515-rocm10:aiter-gfx1151-current-main-v3 \
  sha256:e9647f36b4659b3272c1689fcbb85fee17002a7ead9516c09f3e310ec9e719e6

vllm_compact=haloloom-vllm-full-gfx1151:v0.1.0-rc1
sglang_compact=haloloom-sglang-full-gfx1151:v0.1.0-rc1
quark_compact=haloloom-quark-golden-base-gfx1151:v0.1.0-rc1
vllm_runtime=haloloom-vllm-full-gfx1151:${VERSION}-runtime
sglang_runtime=haloloom-sglang-full-gfx1151:${VERSION}-runtime
vllm=haloloom-vllm-full-gfx1151:${VERSION}
sglang=haloloom-sglang-full-gfx1151:${VERSION}
quark=haloloom-quark-rocm10-gfx1151:${VERSION}
aiter=haloloom-aiter-tools-full-gfx1151:${VERSION}

docker build --progress=plain -f docker/full-vllm/Dockerfile -t "$vllm_compact" .
docker build --progress=plain -f docker/full-sglang/Dockerfile -t "$sglang_compact" .
docker build --progress=plain -f docker/full-quark-base/Dockerfile -t "$quark_compact" .

docker build --progress=plain -f docker/full-vllm-release/Dockerfile \
  --build-arg VLLM_WHEEL_SHA256="$VLLM_WHEEL_SHA256" \
  --build-arg LOWBIT_WHEEL_SHA256="$LOWBIT_WHEEL_SHA256" \
  -t "$vllm_runtime" .
docker build --progress=plain -f docker/full-sglang-release/Dockerfile \
  --build-arg LOWBIT_WHEEL_SHA256="$LOWBIT_WHEEL_SHA256" \
  -t "$sglang_runtime" .
docker build --progress=plain -f docker/ecosystem/Dockerfile \
  --build-arg BASE_IMAGE="$vllm_runtime" \
  -t "$vllm" .
docker build --progress=plain -f docker/ecosystem/Dockerfile \
  --build-arg BASE_IMAGE="$sglang_runtime" \
  -t "$sglang" .
docker build --progress=plain -f docker/quark/Dockerfile -t "$quark" .
docker build --progress=plain -f docker/aiter-tools/Dockerfile -t "$aiter" .

printf 'HALOLOOM_IMAGES_BUILT version=%s\n' "$VERSION"
printf '%s\n' "$vllm" "$sglang" "$quark" "$aiter"
