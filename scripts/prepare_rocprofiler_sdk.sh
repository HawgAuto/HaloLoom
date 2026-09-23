#!/usr/bin/env bash
# Prepare exact public source inputs; compilation itself is offline.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[ "$#" -eq 1 ] || { printf 'usage: %s NEW_ABSOLUTE_WORKSPACE
' "$0" >&2; exit 64; }
WORK=$1
case "$WORK" in /*) ;; *) printf 'workspace must be absolute
' >&2; exit 64;; esac
[ ! -e "$WORK" ] || { printf 'workspace already exists; refusing overwrite
' >&2; exit 65; }
mkdir -p "$WORK"
git init "$WORK/upstream"
git -C "$WORK/upstream" remote add origin https://github.com/ROCm/rocm-systems.git
git -C "$WORK/upstream" -c protocol.version=2 fetch --depth 1 --filter=blob:none origin 6b0e43f341195e203754e08f850e437ff2fc09f9
git -C "$WORK/upstream" sparse-checkout init --cone
git -C "$WORK/upstream" sparse-checkout set projects/rocprofiler-sdk projects/rocprofiler-systems/cmake/Modules
git -C "$WORK/upstream" checkout --detach FETCH_HEAD
[ "$(git -C "$WORK/upstream" rev-parse HEAD)" = 6b0e43f341195e203754e08f850e437ff2fc09f9 ]
mapfile -t modules < <(git -C "$WORK/upstream" config -f .gitmodules --get-regexp '^submodule\..*\.path$' | cut -d ' ' -f 2-)
for module in "${modules[@]}"; do
  case "$module" in projects/rocprofiler-sdk/external/*)
    git -C "$WORK/upstream" submodule update --init --depth 1 -- "$module";;
  esac
done
python3 - "$WORK" <<'PY'
from pathlib import Path
import shutil,sys
w=Path(sys.argv[1])
shutil.copytree(w/'upstream/projects/rocprofiler-sdk',w/'source/projects/rocprofiler-sdk',ignore=shutil.ignore_patterns('.git'))
(w/'cmake-modules').mkdir()
shutil.copy2(w/'upstream/projects/rocprofiler-systems/cmake/Modules/FindNUMA.cmake',w/'cmake-modules/FindNUMA.cmake')
PY
mkdir "$WORK/deps"
curl --fail --location --proto '=https' --tlsv1.2 --max-time 180 \
  https://rocm-third-party-deps.s3.us-east-2.amazonaws.com/otf2-3.0.3.tar.gz \
  -o "$WORK/deps/otf2-3.0.3.tar.gz"
printf '18a3905f7917340387e3edc8e5766f31ab1af41f4ecc5665da6c769ca21c4ee8  %s
' "$WORK/deps/otf2-3.0.3.tar.gz" | sha256sum --check
python3 - "$WORK" <<'PY'
from pathlib import Path
import sys,tarfile
w=Path(sys.argv[1]);d=w/'deps/extracted';d.mkdir()
with tarfile.open(w/'deps/otf2-3.0.3.tar.gz') as f:
    if sum(m.size for m in f.getmembers())>256*1024*1024:raise ValueError('OTF2 archive exceeds limit')
    f.extractall(d,filter='data')
roots=list(d.iterdir())
if len(roots)!=1 or not roots[0].is_dir():raise ValueError('unexpected OTF2 layout')
roots[0].rename(w/'deps/otf2-source')
PY
curl --fail --location --proto '=https' --tlsv1.2 --max-time 180 \
  https://github.com/NixOS/patchelf/releases/download/0.18.0/patchelf-0.18.0.tar.bz2 \
  -o "$WORK/deps/patchelf-0.18.0.tar.bz2"
printf '1952b2a782ba576279c211ee942e341748fdb44997f704dd53def46cd055470b  %s\n' "$WORK/deps/patchelf-0.18.0.tar.bz2" | sha256sum --check
python3 - "$WORK" <<'PY'
from pathlib import Path
import sys,tarfile
w=Path(sys.argv[1]);d=w/'deps/patchelf-extracted';d.mkdir()
with tarfile.open(w/'deps/patchelf-0.18.0.tar.bz2') as f:
    if sum(m.size for m in f.getmembers())>32*1024*1024:raise ValueError('patchelf archive exceeds limit')
    f.extractall(d,filter='data')
roots=list(d.iterdir())
if len(roots)!=1 or not roots[0].is_dir():raise ValueError('unexpected patchelf layout')
roots[0].rename(w/'deps/patchelf-source')
PY
# Apply inside a real temporary Git tree; never use no-index skip semantics.
git -C "$WORK/source" init
git -C "$WORK/source" apply --check "$ROOT/patches/rocprofiler-sdk/mixed-aql-accounting.patch"
git -C "$WORK/source" apply "$ROOT/patches/rocprofiler-sdk/mixed-aql-accounting.patch"
cp "$ROOT/docker/rocprofiler-sdk/build-sdk.sh" "$WORK/build-sdk.sh"
printf 'SDK_SOURCE_PREPARED %s
' "$WORK"
