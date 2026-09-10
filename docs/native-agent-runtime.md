# Native agent runtime in source-current images

The source-current payload includes the qualified native Codex CLI, its official
sidecars, license/notice files, a file-hash manifest and source provenance. The
patched CLI comes from `ff1c753381773e8c22e1739ab29709dc7589ba8c` (upstream `rust-v0.153.4`). The matching
source archive, stored at `native-agent-source/codex-amd-source-rust-v0.153.4.tar.gz`
inside the build-input payload, retains upstream build instructions and Cargo/Bazel lock files.
Build the application with `cargo build --locked --release -p codex-cli --bin codex`
from `codex-rs/`, using the toolchain and dependencies specified by that tree.
Sidecars are preserved byte-for-byte from the official runtime, not modified.

## Use and authentication

Follow the [normal installation instructions](../README.md). Compose selects
`/opt/haloloom/codex-amd/bin/codex` inside the image. Existing host Codex OAuth
authentication is mounted read-only and copied into an ephemeral container home.
Credentials are not distributed in the payload or image. `agent-check` works in
the workbench and Quark entrypoints without acquiring a GPU lease.

`HALOLOOM_CODEX_BIN_IMAGE` is an explicit image-CLI override. Compose defaults it
to the bundled CLI. An explicitly empty value permits legacy
`HALOLOOM_CODEX_BIN_HOST` selection. A configured missing override fails closed,
rather than silently selecting another executable. This does not add a model or
provider fallback; those choices remain explicit.

## Build and verification

The [source-current Docker recipe](../docker/source-current/Dockerfile) and
[release-input builder](../scripts/build_release_inputs.py) consume the public,
hash-pinned payload. The [native runtime verifier](../scripts/install_native_agent_runtime.py)
checks the complete file set, hashes, executable modes and actual CLI version.
It rejects undeclared files, traversal and symlinks. These build-time checks are
CPU-only and do not claim new GPU performance qualification.

The sandbox patch is scoped to AMD KFD/render devices. Installing it does not
authorize exposing NVIDIA devices, relaxing general filesystem/network rules,
or bypassing per-workload hooks. Runtime bytes must match the associated
boundary and real-model qualification receipts.

## Resume boundaries

A completed native GEAK `result.json` is recovered as **unvalidated** by the parent;
the parent's own rebench decides acceptance. A previous terminal sweep or final
profile cannot substitute for the current resume leg. A completed PRELUDE
analysis is not replayed just to recover a failed final profile.

`HYPERLOOM_CLOSE_POST_OPT_ROOFLINE_TIMEOUT_SEC` extends the historical 600-second
final-profile default for a cold real model. It must be finite and positive and
is clipped to the remaining session budget. A longer limit is not evidence of
successful profiling; the resulting artifact is still required.

Ray preflight canonicalizes an unambiguous ROCm mask to `HIP_VISIBLE_DEVICES`.
Conflicting masks fail before any visibility mutation. Do not independently nest
the global GPU flock around `workbench-entrypoint`: the entrypoint owns that
lease for the optimizer and its descendants.
