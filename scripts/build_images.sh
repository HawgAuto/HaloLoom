#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Source overlays alone do not include Quark's compiled native extension.
set -- "$@" --package-quark-native
exec python3 "$ROOT/scripts/build_release_inputs.py" "$@"
