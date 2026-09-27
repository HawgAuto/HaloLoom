# Run-fix reconciliation: source changes and operational boundaries

This document accompanies source-level reconciliation of fixes found while
using HaloLoom. **A published source commit is not a rebuilt image, a released
installer update, a performance result, or permission to change a live job.**
The stable image manifest stays unchanged until matching images are published
and read back from the registry. See [complete source-bound builds](full-release-builds.md).

## Published source checkpoints (not image releases)

These source changes are available on `fix/run-reconciliation-20260926`.
Exact commits, trees and verification scope are recorded separately in the
[source checkpoint manifest](../manifests/source-fixes-20260926.json), which does
not replace the stable installer/image manifest:

- [Hyperloom `b728b8fcb90ddd14fcdff576e9eb8011a801a1ae`](https://github.com/hstolte11-collab/Hyperloom/commit/b728b8fcb90ddd14fcdff576e9eb8011a801a1ae):
  startup/loader and Ray recovery, source roots, attribution/report freshness,
  failed-profile handling and the explicit GEAK artifact-path handoff.
- [GEAK `8c116e81ed4005a48afa156121f79cf8ea23c776`](https://github.com/HawgAuto/GEAK/commit/8c116e81ed4005a48afa156121f79cf8ea23c776):
  matching explicit input selection and the default-off, separately gated
  local-serving worker/device contract for the audited Codex runtime.

- [Codex `c693d79428b1c3f71fbc74bf16df88f369e3cf08`](https://github.com/HawgAuto/codex/commit/c693d79428b1c3f71fbc74bf16df88f369e3cf08):
  separately default-off local interface discovery, scoped to the proxy-routed,
  explicit-local-IPC, zero-capability command context. The bounded offline native
  sandbox test run passed 174 tests with none skipped; parent review verified
  the exact source delta and hashed test log without repeating compilation.
- [vLLM `ab3c2dc13266e6f85fbdda8af95eaec11fb30bd8`](https://github.com/HawgAuto/vllm/commit/ab3c2dc13266e6f85fbdda8af95eaec11fb30bd8):
  explicit profiler stack control/lifecycle cleanup, native speculative token
  metadata scalar normalization, and excluded Quark embedding preservation.
  Four CPU **source/AST contract checks** passed again under parent execution;
  these are not a model execution, leak-duration or GPU acceptance test.

[Quark `8b6d73c1f4a486c172cd208cd72ed6e651947c0c`](https://github.com/hstolte11-collab/Quark/commit/8b6d73c1f4a486c172cd208cd72ed6e651947c0c)
was already public on `release/haloloom-v0.1.4`. Its anonymous source/tree readback
and four preservation regression files were verified; this did not rerun PTQ or
publish another Quark commit.

Parent reruns in a no-network, no-GPU container passed 55 Hyperloom Python tests,
133 GEAK Python tests, 14 GEAK Node regressions and 84 GEAK runtime self-checks.
Anonymous clean clones matched the published commit and tree identities. A
synthetic path-contract test exercised the actual Hyperloom bundle builder into
GEAK's mapper and prompt, including rejection of incomplete/removed artifacts.
That test is not model inference or content-hash sealing. Original baseline
tests were not changed. Source lint is not represented as complete: Ruff was
unavailable, and a previously accepted new Ray regression retains one trailing
blank-line whitespace warning.

The component reconciliation is ongoing. TraceLens's proposed successor is
**held from publication** because the existing `xdit_hunyuanvideo` CSV reference
test passes at its base and fails with the proposed attribution changes. The
InferenceX/Magpie launcher deltas are still under ownership/source review.
This checkpoint does not assert that all component forks, wheel archives,
installed runtime files or image pins have been refreshed. In particular,
GEAK's repaired `interface/` files require a source/runtime refresh, not just
replacement of its Python package wheel.

## Source and installed-runtime identity

- Commit the reviewed framework source before creating specialist worktrees.
  A worktree starts from a commit, not another directory's dirty files. Compare
  the source commit, tree and installed-file hashes; a source checkout next to
  stale `site-packages` is not an installed repair.
- Preserve the native extension donor and its ABI when composing a Python-source
  repair. Record native donor identity separately. Align reinstallable wheel
  mirrors as well as the currently installed files.
- Preserve the image's working directory, shell, UID, entrypoint and environment
  through compaction. Use root for root-owned installation steps only, then
  return to the non-root runtime user. Do not grant runtime capabilities to make
  a build or sandbox test pass.
- Preserve in-tree source symlinks during source copying. Reject path traversal,
  escaping symlinks and unsupported archive members; do not dereference a link
  into host files. Verify the installed copy, not only the source archive.
- A registry manifest digest and Docker's local image/config ID are different
  identities. For an explicitly local build, tag the verified local image ID,
  read the tag's exact ID back, and disable pulling. Do not use a bare local
  `sha256:<image-id>` as if it were a public `FROM` reference. Public recipes need
  a pullable digest-pinned registry base.

## Runtime and interpreter isolation

- Preserve a supplied nonempty `LD_LIBRARY_PATH`. Default construction must not
  silently reorder an operator's qualified runtime closure. Avoid loading two
  COMGR/LLVM SDK closures into the same process.
- Full-runtime loader paths are in the **opt-in**
  `docker/full-release/compose.runtime.yaml`. They are not an automatic override
  for stable images and do not choose an image by themselves.
- Keep Quark's quantizer interpreter separate from the serving interpreter.
  Install model-loader/Transformers dependencies in the interpreter that uses
  them; do not upgrade the serving dependency set incidentally.
- A serving profiler registration or Torch preload must not leak into the
  quantizer. Remove only the explicitly owned profiler/preload settings in the
  appropriate child environment, not arbitrary operator configuration.
- `LD_LIBRARY_PATH` is a runtime loader path, not a substitute for the compiler's
  `LIBRARY_PATH` / `-L` search paths. A clean-cache AITER compile/import/native
  execution check is distinct from finding AITER already installed.
- Some AITER versions use a second C++ template/cache root. `AITER_JIT_DIR` alone
  may not redirect it. Set a worker-owned `AITER_ROOT_DIR` only with the matching
  source/template layout and verify that version's behavior. This is a cache
  workaround, not a reason to allow writes across the operator's home directory.

## Profiling and trace interpretation

- Explicit `torch_profiler_with_stack=false` must remain false even when detailed
  tracing is enabled. Detailed tracing and stack capture are different controls.
- Stop/export cleanup must release profiler state and traceback reference cycles.
  A few successful windows are finite evidence, not proof of indefinite leak
  freedom.
- Bound detailed capture windows and collect host-global RAM/GTT telemetry.
  Shared-memory GPU allocations are not fully described by a container's RSS or
  memory limit. Separately rearmed windows are not one contiguous capture.
- Verify start/stop controls from ordered HTTP success events in the exact
  server PID's log interval for each window. Client prose saying “started” is
  not server-side evidence. Preserve failures and window boundaries.
- Prefer temporal workload traces over metadata sidecars during discovery;
  classify paths relative to the capture root, not arbitrary ancestor names.
- Carry graph-attribution incompleteness into durable reports. Missing,
  malformed, ambiguous or unassociated events must not become authoritative
  source ownership through a plausible symbol-name match.
- Exact-replay admission is scoped to exact replay. It does not automatically
  prohibit independently qualified source authoring, nor does source authoring
  establish exact-replay coverage.
- When resuming, archive stale inherited reports by content hash before atomically
  regenerating them. Mark incomplete safety-net reports as incomplete.

## Resumption, dispatch and evidence

- A zero-hour unbounded objective is distinct from a negative/invalid duration
  or a zero-duration objective with a finite target. Represent absence of a
  deadline natively; do not convert floating-point infinity to an integer.
- A successful `ray status` exit is insufficient when there are no active nodes.
  Infrastructure failure is not a model-patch failure or evidence of authoring
  progress. Recovery may restart only an owned local empty head, never an
  explicitly configured remote cluster.
- Preserve the authoritative framework source root through retries and
  integration. Do not harvest heartbeat/completion files as code changes, or
  promote inherited stale patch files after a specialist produced no deliverable.
- Treat failed tasks as terminal. Recovery requires a fresh idempotency key and
  preservation of the task's lanes, side effects and TTL. A restart must not
  duplicate dispatch or reset an already-consumed budget.
- Persist one continuation-entry receipt at actual entry, not during preparatory
  work. Preserve the saved budget and its rounding/floor semantics. Session IDs,
  frozen DBs and controller state remain private operator artifacts.
- Pass TraceLens artifact paths explicitly across the GEAK handoff. An explicit
  bundle that is missing, malformed or mixed-root must fail closed, not fall back
  to discovery of a different directory. The current generic handoff validates
  keys, artifact types, existence and analysis-root coherence; it does **not**
  cryptographically seal file contents. Preserve upstream artifact hashes in
  separate provenance records rather than claiming this path contract checks them.
- Failed profiling subprocesses require artifact validation. A genuine partial
  measurement and an empty or arbitrary-byte report are different outcomes.
- Environment-gated rewrites must declare their switches so switch-off parity
  and attribution checks can be performed.
- Controllers using `os.pidfd_open` must probe the exact interpreter they will
  execute. The capability is not established by another Python on `PATH`.

## Authentication and private harnesses

Keep shared credentials read-only. A campaign-specific, owner-authorized
short-lived-token projection is not a portable login mechanism: its provider,
client/account identity, lifetime and credential-store assumptions must be
validated separately. Never publish token values, refresh tokens, auth files,
private profile settings or live-auth probe artifacts with a software fix.
Remove ephemeral projections at exit. This reconciliation documents that
boundary; it does not copy the private campaign authentication launcher into
the product or change any user's credentials.

Similarly, evaluator request previews must use the evaluator's native chat
handler and tokenizer. A broken preview does not demonstrate a broken evaluator.
Private evaluation harnesses and saved responses are not component source.

## Native MTP and graph settings

Preserve a qualified launch contract instead of silently substituting eager
mode or disabling speculative decoding to get a process to start. The native
V2 contract used breakable graphs, AMD Triton FlashAttention and `PIECEWISE`
graph mode; its environment and compilation settings are coupled to the exact
runtime revision. This is **not a universal default recipe** for other models
or images. A restored environment still needs installed-runtime verification.

Keep separate claims for metadata scalar correctness, draft/proposer/cache
checks, full-target scheduler/generation, quality and throughput. Do not revive
a rejected QSA/no-FlashAttention fallback or bypass drafting/cache guards under
the label of a repair. Source-identity/review-export gaps, reducer questions and
unqualified speculative paths stay open until their own evidence closes them.
