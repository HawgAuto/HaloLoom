# Qualification contract

HaloLoom separates build, import, platform, model-request, route and operational evidence. Passing an earlier gate never implies a later gate.

## Current v0.1.1 evidence

`qualification/receipts/release-closeout-v0.1.1.json` is the final-image/runtime/anonymous-registry snapshot. It binds the original vLLM native profile action, the unchanged SGLang/Quark five-request substring canaries, and the four final HIP/Triton toolchain paths. Those model-runtime canaries do not replace the stricter exact-output/custom-route gates below or promote the rejected Quark candidate. `optimizer-internal-close-v0.1.1.json`, `native-profiler-historical-v0.1.1.json`, and `quark-native-evaluation-v0.1.1.json` preserve separate historical successes and limits. Source/tag and fresh-install verification occur after this runtime snapshot.

## Release gates

### Source and packaging

- every source component pinned by full commit SHA;
- recursive source manifests match the build contexts;
- public-data/secret scan passes;
- Hyperloom wheel contents checker passes;
- core framework wheels contain no optional low-bit consumer module;
- native extension code-object inventory is exactly `gfx1151`;
- image and release artifact checksums are recorded and read back.

### Static image

Run without `/dev/kfd` or `/dev/dri`:

- exact Python/Torch/ROCm/HIP versions;
- framework package import;
- package/module import without device discovery;
- Hyperloom/Quark entrypoints and external agent plug-in resolution where applicable;
- no `HSA_OVERRIDE_GFX_VERSION`;
- zero remaining allowlisted non-target architecture assets.

### Physical gfx1151

Every GPU container must hold `/run/lock/hermes-vllm-gfx1151.lock`, run `fuser /dev/kfd` after acquiring it, use native `gfx1151`, and leave `HSA_OVERRIDE_GFX_VERSION` unset.

The compact release images use one coherent runtime root: `ROCM_PATH`, `ROCM_HOME` and `HIP_PATH` are `/opt/rocm/core-10.0`. Keep the complete loader settings supplied by Compose. vLLM additionally prepends its exact wheel-provided `host-math/lib` dependency directory and registers its existing Kineto client through `ROCP_TOOL_LIBRARIES`; this qualified dependency closure is intentional, not permission to mix arbitrary SDK roots. SGLang uses both `SGLANG_CACHE_DIR=/workspace/.cache/sglang` and `SGLANG_JIT_CACHE_DIR=/workspace/.cache/sglang/jit` from Compose. Its two native cache roots are independent; `XDG_CACHE_HOME` or `TRITON_CACHE_DIR` alone does not replace them. Private test launchers must preserve these shipping settings and the writable workspace mount.

For vLLM and SGLang, require:

1. exact image ID/digest and installed wheel hashes;
2. Torch reports Radeon 8060S and `gfx1151`;
3. framework platform/parser starts through the exact release image;
4. the pinned real model loads;
5. health/model listing names that model;
6. a request-owned OpenAI-compatible response with nonzero usage;
7. exact output oracle;
8. clean server exit and no stale container/device owner.

SGLang uses Triton attention with CUDA graphs disabled and AITER disabled for the qualified BF16 route.

For Quark, the compact golden base must retain the exact Quark/Torch/source identity. The final image must expose the original `quantization-agent` workflow through the reviewed faithful Hyperloom wheel. A device/import/entrypoint smoke is runtime proof only; a full PTQ claim still requires manifest, calibration, real PTQ/export, original validators and honest evaluation classification.

`qualification/receipts/quark-final-public-wheel-runtime-handoff-v0.1.0.json` binds final public-wheel image physical gfx1151 execution, absent bundled agent CLIs, and unchanged golden identity to the prior real INT8 PTQ/export lifecycle. It explicitly records that the prior artifact was quality-rejected and that no fresh provider, plan or PTQ run was performed in the final image. The older receipt is retained as superseded historical evidence.

For AITER tools, require package/device import and the separately declared JIT module canaries. Do not promote SGLang AITER attention: the retained BF16 GQA2/head-size-128 attempts failed in CK prefill compile and paged-decode device execution.

`qualification/receipts/aiter-final-bounded-v0.1.0.json` records the final bounded result: device import, module-core JIT/load, gemm-common operation/JIT, and RMSNorm operation/numerical/JIT pass. The sample module itself compiles/loads, but greedy sampling fails its exact argmax oracle and is unavailable. AITER attention remains unavailable. Neither unavailable operation is exposed as a supported default.

### Operational closeout

- remove only request-owned containers/processes;
- verify no stale KFD owner or lock holder;
- do not modify production model registries/services;
- preserve failed attempts as separate epochs;
- publish no image until its release candidate completes its own fresh physical gate.

## Historical component evidence

- Final Hyperloom readiness authority is commit `6f67fbef…` plus its public-release portability successor, not the earlier `0c32b463…` wheel epoch.
- Magpie current-main port: 404 root tests; 16 focused runner tests; independent review passed.
- GEAK full-readiness commit `506b5796…` has a real gfx1151 candidate compile/device/correctness lifecycle and 451 interface tests plus 8 subtests.
- IntelliKit Metrix commit `2f61453a…` has native gfx1151 registration and Strix-specific counter formulas; 17 focused mocked gfx1151 unit tests pass. Physical Metrix profiling remains a separate workbench-image gate.
- AITER package/JIT/non-attention scope is physically qualified at source commit `a343a105…`; attention remains unavailable for the tested geometry.

`qualification/readiness/FINAL-CLOSEOUT.json` is the sealed readiness status authority. `qualification/readiness/FUNCTIONAL-TARGET-MATRIX.json` records all 23 targets (22 editable, one control-only) with no fallback or promotion authority. It establishes functionally complete, production-ready-but-not-activated optimizer infrastructure; it does not claim a new performance win or candidate adoption.

Final local W4A8 route receipts are:

- `qualification/receipts/vllm-full-w4a8-final-v0.1.0.json`
- `qualification/receipts/sglang-full-w4a8-final-v0.1.0.json`

Each binds its historical final local image ID, model revision, exact `RDNA35_OK` response, 16 eligible layers, positive asynchronous physical dispatches, event completion, zero fallback/foreign rows, coherent `/opt/rocm/core-10.0` runtime, and clean teardown. They do not claim a performance win or production activation. These historical local-image receipts predate registry readback; current public image identities are recorded separately in `manifests/components.json`.

`qualification/route-status-v0.1.0.json` remains the earlier full-image W4A8 publication receipt. The later sealed readiness matrix additionally closes all six SGLang-native methods with real request-owned route evidence and closes the 23-target functional registry. Neither authority claims a performance win or production activation.
