# Accepted InferenceX launcher repairs

This is a source-only, explicitly applied patch against
`SemiAnalysisAI/InferenceX` commit
`3d5581562f643f9bdeb8410cd924e2c70906c966`. It is carried here because the
launcher belongs to InferenceX and no owned InferenceX fork is available.
Magpie consumes this launcher; an unrelated Magpie source edit would not fix it.

The patch preserves the accepted profiling/evaluator repairs and replaces four
**client URLs** using `0.0.0.0` with `127.0.0.1`. Server bind arguments are not
changed. It also carries five additive CPU-only source/launcher regressions.

See [manifest.json](manifest.json) for the patch digest, exact base tree, before
and after launcher hashes, and the resulting patched tree identity. The local
preparation commit recorded there is provenance, **not a publicly fetchable
InferenceX fork ref**. The public deliverable is this patch in HaloLoom.

## Verify and apply in a new checkout

From the HaloLoom repository root, using a Python environment with pytest:

```bash
PATCH="$PWD/patches/inferencex/accepted-launcher-repairs.patch"
printf '%s  %s\n' \
  a1938f70fc5c53603dd1fdf9d052b78741da21ce5afe69ae118ff5cbaac594ea \
  "$PATCH" | sha256sum -c -

INFERENCEX_SRC="$HOME/src/inferencex-launcher-check"
test ! -e "$INFERENCEX_SRC"
git init "$INFERENCEX_SRC"
git -C "$INFERENCEX_SRC" fetch --depth 1 \
  https://github.com/SemiAnalysisAI/InferenceX.git \
  3d5581562f643f9bdeb8410cd924e2c70906c966
git -C "$INFERENCEX_SRC" checkout --detach FETCH_HEAD
git -C "$INFERENCEX_SRC" apply --check "$PATCH"
git -C "$INFERENCEX_SRC" apply "$PATCH"
bash -n "$INFERENCEX_SRC/benchmarks/benchmark_lib.sh"
python -m pytest -q \
  "$INFERENCEX_SRC/tests/test_haloloom_benchmark_launcher.py"
```

The five checks cover pinned/accepted source hashes, the four URL substitutions,
unchanged server bindings, the health helper's actual argument construction,
and evaluator dependency failure propagation after a caller changes directory.
They do not start a model server, download evaluator dependencies, or establish
model quality, throughput, profiling completeness, or upstream acceptance.

## Installation boundary

This patch is **not automatically applied by the stable installer**. A future
runtime assembly must deliberately apply and verify it against the pinned
InferenceX source, and refresh retained launcher copies as well as the source
checkout. Existing running workers and frozen build packets are not modified
by publishing this file. Do not double-apply the patch to an already repaired
launcher or revert newer unrelated changes to make an old patch fit.
