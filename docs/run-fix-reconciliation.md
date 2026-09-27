# Run-fix reconciliation: source changes and operational boundaries

This document accompanies source-level reconciliation of fixes found while
using HaloLoom. **A published source commit is not a rebuilt image, a released
installer update, a performance result, or permission to change a live job.**
The stable image manifest stays unchanged until matching images are published
and read back from the registry. See [complete source-bound builds](full-release-builds.md).

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
- Pass sealed TraceLens artifacts and hashes explicitly across the GEAK handoff.
  An explicit bundle that is missing, malformed, mixed-root or hash-mismatched
  must fail closed, not fall back to discovery of a different directory.
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
