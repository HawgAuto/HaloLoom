#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$ROOT"
unset HSA_OVERRIDE_GFX_VERSION

PULL_IMAGES=1
SYNC_SOURCES=0
INCLUDE_BUILD_SOURCES=0
INCLUDE_AITER=0
AGENT=auto

usage() {
  cat <<'EOF'
Usage: ./scripts/install.sh [options]

Options:
  --agent auto|claude|codex|hermes
                              Select an existing host agent CLI (default: auto).
  --no-pull                   Configure only; do not pull OCI images.
  --sync-sources              Materialize exact public component source mirrors.
  --include-build-sources     Also mirror vLLM/SGLang/Quark/AITER build sources.
  --include-aiter             Pull the optional AITER tools image.
  -h, --help                  Show this help.

The default path installs no host Python packages and no agent CLI. It detects
an existing Claude Code, Codex, or Hermes installation and writes only bind-
mount/configuration paths into .env.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      [[ $# -ge 2 ]] || { echo "ERROR: --agent requires a value" >&2; exit 2; }
      AGENT="$2"
      shift 2
      ;;
    --no-pull)
      PULL_IMAGES=0
      shift
      ;;
    --sync-sources)
      SYNC_SOURCES=1
      shift
      ;;
    --include-build-sources)
      SYNC_SOURCES=1
      INCLUDE_BUILD_SOURCES=1
      shift
      ;;
    --include-aiter)
      INCLUDE_AITER=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

python3 scripts/preflight.py --allow-busy --write-env .env
python3 scripts/detect_agent_plugins.py \
  --env-file .env \
  --state-dir .haloloom-agent-plugins \
  --agent "$AGENT"

# shellcheck disable=SC1091
source .env
mkdir -p artifacts workspace components .haloloom-agent-plugins
# Docker creates missing bind sources as root. Prepare the HF cache as the
# installing/runtime user, including Xet's independent default under HF_HOME.
for cache_dir in "$HF_HOME" "$HF_HOME/hub" "$HF_HOME/datasets" "$HF_HOME/xet"; do
  if ! mkdir -p "$cache_dir" || [[ ! -w "$cache_dir" || ! -x "$cache_dir" ]]; then
    printf 'ERROR: Hugging Face cache is not writable by the runtime user: %s\n' "$cache_dir" >&2
    exit 1
  fi
done
chmod 0755 scripts/haloloom

if [[ "$SYNC_SOURCES" == 1 ]]; then
  SYNC_ARGS=()
  if [[ "$INCLUDE_BUILD_SOURCES" == 1 ]]; then
    SYNC_ARGS+=(--include-build-sources)
  fi
  python3 scripts/sync_sources.py --root components "${SYNC_ARGS[@]}"
fi

if [[ "$PULL_IMAGES" == 1 ]]; then
  pull_services=(vllm sglang quark)
  if [[ "$INCLUDE_AITER" == 1 ]]; then
    pull_services+=(aiter-tools)
  fi
  pull_log=$(mktemp)
  if ! docker compose pull "${pull_services[@]}" 2>&1 | tee "$pull_log"; then
    if grep -qiE "unauthorized|denied|authentication required" "$pull_log"; then
      cat >&2 <<'EOF'
ERROR: the registry refused the image pull (unauthorized/denied).

HaloLoom images are published as PUBLIC packages under
  https://github.com/orgs/HawgAuto/packages
and need no login. If you see this, either the package is not public yet
(report it: https://github.com/HawgAuto/HaloLoom/issues) or a stale
`docker login ghcr.io` credential on this machine is being sent and rejected;
run `docker logout ghcr.io` and retry ./scripts/install.sh.
EOF
    fi
    rm -f "$pull_log"
    exit 1
  fi
  rm -f "$pull_log"
fi

docker compose config --quiet
printf 'HALOLOOM_INSTALL_OK version=%s workspace=%s agent=%s\n' \
  "$HALOLOOM_VERSION" "$HALOLOOM_WORKSPACE" "$HALOLOOM_AGENT_PROFILE"
