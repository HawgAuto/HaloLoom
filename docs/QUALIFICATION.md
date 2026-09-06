# Test results and limitations

This is the detailed verification reference for HaloLoom. For installation and everyday use, start with the [README](../README.md) and [user guide](USAGE.md).

Build success, package imports, model responses, kernel execution, and model quality are different tests. A pass in one does not imply a pass in the others. The original evidence records below retain exact configurations and outcomes, including earlier failed attempts.

## v0.1.1 summary

| Area | Recorded result | What it establishes |
|---|---|---|
| Public installation | Anonymous clone, release-asset checksums, and installation of four public image identities passed. | A new checkout works on a Docker/Compose-equipped Strix Halo host with an existing Codex CLI. Docker/driver bootstrap was not tested. |
| Test suite | 123 tests passed for the released source and fresh clone. | The release's scoped CPU test suite passed; this is not a model-quality benchmark. |
| Public rebuild | The standard build helper completed using the public archive and pinned bases. | Rebuilt source, installed Python, and native-file hashes matched; OCI metadata/image identities need not be identical. |
| vLLM API | A cached Qwen3.5-0.8B request returned `PARIS`. | Real text-only API delivery with the bounded configuration below, not arbitrary-model or multimodal coverage. |
| vLLM profiling | 16 requests completed at capture delay/max 128/128; 128,912 GPU kernels and 193,713 HIP runtime events were captured. | Native profiling worked in the final release image with its supplied defaults. |
| SGLang and Quark serving | Each completed five model requests. | The existing city-substring response checks passed; they are not exact-format or quality benchmarks. |
| Build tools | Four final HIP/Triton toolchain paths passed checks without GPU devices. | Compiler/native-loader availability, not a claim that every kernel works or improves performance. |

### Published-source and installation checks

These checks used the original release source at [commit `353ae77b2d733fb7292abb771d11ca5e6a44ba10`](https://github.com/HawgAuto/HaloLoom/tree/353ae77b2d733fb7292abb771d11ca5e6a44ba10). All 94 tracked files matched the reviewed tree. Documentation on `main` may change independently; the tag, images, and original evidence remain unchanged by this documentation update.

All three release assets were downloaded anonymously and matched their SHA-256 values. `scripts/install.sh --agent codex --include-aiter` pulled all four images with an empty registry credential store. The host already had Docker/Compose and Codex; no host packages or new Python environment were installed.

The default `scripts/build_images.sh` completed from the public release archive and pinned bases. All three rebuilt runtimes matched the published images' embedded source, installed Python, and native-file hashes. AITER retained its digest. Build/provenance metadata can change OCI identities; this is not a bit-identical image-index claim. The API check used the **published vLLM image**, not a newly served instance of the rebuilt image.

The unmodified `scripts/serve.py` served cached Qwen3.5-0.8B revision `2fc06364715b967f1860aea9cf38778875588b17`. The response was `PARIS`, with 31 prompt and 3 completion tokens. Model settings were a 512-token context, one sequence, fixed `--kv-cache-memory-bytes 268435456`, `--language-model-only`, BF16, eager loading/execution, and Triton attention. Local Compose overrides restricted the test to loopback, read-only model data, no credential mounts, and bounded container resources; these restrictions are not all defaults in the public Compose file.

The automatic UMA sizing attempt hit a free-memory-change guard. The fixed-KV success does not establish broad automatic-sizing or multimodal support. Full optimizer/PTQ work was not repeated from the anonymous checkout, and no candidate was promoted. Cleanup removed the test container and released the GPU lock; existing production processes, model registry, and service health were preserved.

The original installation/rebuild/API verification receipt has SHA-256 `a8be442bb253b52052c53f56b26be19fce5cba853c58a49634dca2670a3066cf`. This section retains the verification details previously included in the public release notes; the original receipt and historical runtime records were not rewritten.

### Original runtime and optimizer records

The [final runtime record](../qualification/receipts/release-closeout-v0.1.1.json) binds the vLLM profile, SGLang/Quark request checks, final toolchain checks, and anonymous image-registry readback. It was recorded before the source publication and installation checks above.

Separate historical records cover the [completed optimizer run](../qualification/receipts/optimizer-internal-close-v0.1.1.json), [earlier native-profiler test](../qualification/receipts/native-profiler-historical-v0.1.1.json), and [Quark evaluation](../qualification/receipts/quark-native-evaluation-v0.1.1.json). The optimizer's actual internal `CLOSE` remains valid and was not rerun. Its disabled evaluation/knowledge-base options and skipped GEAK native-budget work describe that specific run, not universal feature coverage. Successful serving does not change the Quark candidate's recorded quality rejection. No quality or performance improvement is inferred from these runtime checks.

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
