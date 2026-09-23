# SDK mixed-AQL accounting and request-clock repair

This is a **scoped, opt-in profiling repair**, not a new general serving release.
The existing installer/Compose image pins and optimizer defaults are unchanged.
The source patch belongs to ROCm's SDK; HaloLoom owns its packaging and request
attribution helpers. No vLLM or Torch source changes are part of this release.

## What is fixed

ROCm/rocm-systems `6b0e43f341195e203754e08f850e437ff2fc09f9`
(SDK 1.3.5) splits mixed AQL writes for dispatch-counter callbacks. A non-dispatch
singleton increments the asynchronous queue count but registers no completion
handler. The four-line patch balances precisely that empty-session branch.
It does not reorder global finalization or disable graphs/counters.

The request recorder must use `rocprofiler_get_timestamp`, which this SDK binds
to `CLOCK_BOOTTIME`. Do not compare its counter rows to `CLOCK_MONOTONIC_RAW`
and do not reconstruct old request times with a later guessed offset.
`profiling/rocprofiler-sdk/sdk_clock.py` verifies the exact library hash and
brackets every SDK call with BOOTTIME reads. The strict raw reducer additionally
requires stable pre/post PID/start-tick identities and full interval containment.
The `qwen38_metrix_lifecycle.v1` schema is intentionally retained for compatibility;
this release does not claim a generic arbitrary-schema profiler API.

## Source build (no GPU access)

From a fresh public checkout, prepare the pinned public SDK, exact submodule
commits, isolated FindNUMA module, and checksum-verified OTF2 source:

```bash
WORK="$HOME/haloloom-sdk-build"
bash scripts/prepare_rocprofiler_sdk.sh "$WORK"
```

The workspace must not exist. Git, curl, Python 3.12+ and Docker are required.
No host dependencies are installed. Pinned patchelf 0.18.0 is built inside the
CPU-only container, not assumed to be installed on the host or inherited image.
The public compiler/dependency base below reproduced the exact qualified SDK
SHA-256 from a clean build directory:

```bash
SDK_BUILD_IMAGE=ghcr.io/hawgauto/haloloom-vllm-full-gfx1151@sha256:3f80b2e086010a8d5c3c89ed236318f38a2ad3549170799765e29844e3800139
docker pull "$SDK_BUILD_IMAGE"
docker run --rm --network none --cpus 8 --memory 16g --pids-limit 4096   -v "$WORK:/work:rw" --entrypoint /bin/bash "$SDK_BUILD_IMAGE" /work/build-sdk.sh
```

`manifests/rocprofiler-sdk-repair.json` records the original local qualification
image IDs and expected SDK SHA-256. Those local IDs are not registry references;
use the public compiler base above for an independent SDK rebuild. The sanitized
qualification receipt records its byte-identical result. This source release does
not publish the full campaign runtime image or claim that an arbitrary compiler
produces identical bytes. A different build image/output needs its own ABI,
native-control and full-model qualification; never change the expected hash just
to pass the package gate.

## Exact-runtime packaging

The Dockerfile intentionally requires an explicit base. Use a unique local tag
bound to the qualified image ID; do not put a bare `sha256:<id>` in Dockerfile
`FROM`, where it can be interpreted as a Docker Hub repository/tag.

```bash
: "${SDK_RUNTIME_BASE:?Set the qualified immutable runtime base}"
mkdir -p dist/rocprofiler-sdk
cp "$WORK/artifacts/candidate.so" dist/rocprofiler-sdk/candidate.so
docker build --pull=false --network none   --build-arg BASE_IMAGE="$SDK_RUNTIME_BASE"   -f docker/rocprofiler-sdk/Dockerfile -t haloloom-metrix-sdk:local-qualified .
docker run --rm --network none --read-only   --entrypoint /opt/venv/bin/python haloloom-metrix-sdk:local-qualified   -B /opt/haloloom/profiling/rocprofiler-sdk/verify_runtime.py
```

The layer installs the same qualified SDK bytes in **both** the wheel and
core-tree paths and verifies the immutable helpers. It does not hot-patch a
running container, install packages, set global profiler variables, change
model flags, or enable the optimizer. The no-device check proves identity and
clock compatibility, **not** a model request.

## Request integration and reduction

Import `sdk_clock` from `/opt/haloloom/profiling/rocprofiler-sdk` in the profiling
workload controller. Record `stamp()` immediately before and after the request;
retain RAW wall-observation timestamps separately. Record the API source,
`CLOCK_NAME`, `SDK_SHA256`, and stable descendant PID/start-tick snapshots in the
lifecycle. Stop/reap the server normally and retain the profiler's raw CSV.
Run the installed reducer in the same image:

```bash
/opt/venv/bin/python -B /opt/haloloom/profiling/rocprofiler-sdk/reduce_raw_counters.py   --lifecycle /output/lifecycle.json --raw /output/out_counter_collection.csv   --output /output/request-owned.json
```

The current reducer is deliberately OccupancyPercent/Agent 1 specific. It rejects
missing/foreign clocks, wrong SDK hashes, reused PIDs, duplicate/malformed rows,
nonfinite values, crossing intervals, and zero selected rows. It does not claim
that every selected symbol is decode-exclusive or provide a performance score.

## Tests and qualification limits

CPU regression: `python -m pytest tests/test_rocprofiler_sdk_repair.py -q`.
The native source regression and real raw-HSA control/mixed fixtures are under
`tests/native/rocprofiler-sdk/`. Build the fixture in the coherent ROCm 10 image
with that directory mounted at `/fixture`, running `bash /fixture/build.sh`.
Run each GPU fixture only under exclusive ownership and an independent timeout;
require numerical output, raw counters, normal exit and no queue-sync warnings.

Historical installed-original and same-build stock mixed tests reproduced the
residual count; patched mixed and kernel-only controls passed. The unchanged
full-model request completed with finalized counters and ordinary shutdown.
See the sanitized [qualification receipt](../qualification/receipts/rocprofiler-sdk-repair-v1.json).

MTP, optimizer readiness, throughput gains, other SDK versions, general serving
cutover and public image distribution are **not** established by this repair.
Keep rollback images and old failures. Promotion means the dedicated on-demand
profiling consumer selects and exercises this exact runtime, not that a model or
optimizer remains running continuously.
