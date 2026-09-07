# Building HaloLoom

## Use released images unless you need a rebuild

For normal use, run `./scripts/install.sh` from the repository root and follow the [quickstart](../README.md#quickstart). The installer pulls the released images; you do not need to compile ROCm, vLLM, SGLang, or Quark on the host.

This guide is for users who want to reproduce the images, inspect their pinned sources, or understand the build configuration. It requires Docker, network access to the public bases and release assets, and enough local storage for those images and the build cache. It does not install host Python packages or alter existing inference services.

## Rebuild from public inputs (v0.1.1)

From a fresh checkout, run:

```bash
./scripts/build_images.sh
```

It requires the release-provided `manifests/build-inputs.json`; there is no local-image fallback. The schema is exactly `schema_version: 1`, `version: v0.1.1`, one HTTPS overlay archive (`url`, lowercase SHA-256, and matching safe filename), and exactly four image rows: `vllm`, `sglang`, `quark`, and `aiter-tools`. Every base is a full `ghcr.io/...@sha256:<64 hex>` reference and every output has an explicit, unique local tag. The release manifest applies the overlay to the three framework images and leaves `aiter-tools` unchanged.

The entrypoint downloads only the small public overlay archive, verifies its digest before extraction, rejects traversal and non-regular archive entries, and caps total unpacked bytes at 1 GiB. It stages the archive and its original contents under ignored `dist/source-current/`, refusing to overwrite an existing stage. It then pulls each exact public base. Framework rows are rebuilt from the same recipe with no build-time network; the selected Dockerfile target is exactly `vllm`, `sglang`, or `quark`:

```bash
docker build --network none --target <vllm|sglang|quark> \
  --build-arg BASE_IMAGE=ghcr.io/...@sha256:<digest> \
  -f docker/source-current/Dockerfile -t <manifest-local-tag> .
```

The AITER tools row is only tagged from its pulled digest-pinned base. `docker/source-current/Dockerfile.dockerignore` is the explicit safe context; the downloaded tar is retained under `dist/source-current/` for provenance but is not copied into an image. The workflow changes no other production tags and performs no Docker cleanup. Any missing or malformed manifest, unsafe archive, digest mismatch, failed download, or failed Docker command stops the build. `docker/source-current/Dockerfile`, its dockerignore, and the immutable manifest values are release inputs; do not substitute the historical local recipes below.

The new GEAK Codex workflow integration is source-only and is not included in the immutable v0.1.1 release inputs or shipped images. Making it available in images requires a successor source-bound public input packet with a locked Node dependency closure and verification of rebuilt images. Source integration authorization does not authorize release or image publication.

## Build a local qualification candidate (schema 2)

An operator-prepared candidate uses the same entrypoint, Dockerfile, and framework targets:

```bash
./scripts/build_images.sh \
  --archive /absolute/path/candidate-inputs.tar.gz \
  --manifest /absolute/path/candidate.json
```

Schema 2 requires exactly these fields:

- `schema_version`: the integer `2`.
- `version`: `candidate-` followed by an alphanumeric character and then only alphanumeric characters, dots, or hyphens. Release names such as `v0.1.1` are rejected.
- `overlay_archive`: exactly `filename` and `sha256`, with no URL. The filename starts with an alphanumeric character, contains only alphanumeric characters, dots, underscores, or hyphens, and ends in `.tar.gz` or `.tgz`. SHA-256 is 64 lowercase hexadecimal characters.
- `sources`: exactly `GEAK`, `Hyperloom`, and `HaloLoom`; each contains exactly `ref` and `tree`, both full lowercase 40-character Git hashes.
- `images`: the same exactly four rows and validation as schema 1, including digest-pinned public GHCR bases, unique explicit local tags, and the three overlay rows plus the AITER no-overlay row.

`--archive` is required only for schema 2 and is rejected for schema 1. Its absolute path must identify a regular nonsymlink file with the manifest's exact basename. The builder copies it into fresh private temporary staging, limits compressed bytes to the size cap, verifies SHA-256, and uses the existing safe extraction and unpacked size cap. The default cap is 1 GiB; `--max-unpacked-bytes` controls both caps for candidates. No archive download or URL fallback occurs.

The archive must contain a root-level `candidate-sources.json` whose parsed object equals the manifest's `sources` exactly. Duplicate JSON keys in either manifest are rejected. Source mismatch or malformed/unsafe archive inputs fail before any Docker invocation. These pins bind the packet's declared provenance; the parent must prepare the actual offline installer, source payloads, wheels, and locked dependency closures from exact public revisions and independently verify the resulting runtime. The builder does not provision missing dependencies.

Before publishing the prepared stage or pulling/building/tagging images, the builder inspects every destination tag. An existing tag refuses the operation; only Docker's explicit image-not-found response counts as absence. Daemon, authorization, and ambiguous errors fail closed. Use globally unique tags and ensure no concurrent writer claims them: this preflight is not an atomic Docker tag reservation. An existing `dist/source-current/` is still refused, and no cleanup or replacement is performed automatically.

After preflight, the builder pulls the exact public digest bases and builds the same three targets with `--network none`. Schema 2 adds build labels `haloloom.hyperloom_ref`, `haloloom.geak_ref`, and `haloloom.haloloom_ref` from the corresponding source refs, `haloloom.candidate_id` from `version`, and `haloloom.promotion_authority=false`. These override inherited historical values without changing the immutable recipe. The AITER no-overlay row is only retagged from its base: it receives no candidate integration/source labels and cannot claim that integration or those source identities.

A completed candidate build is a local qualification input, not GPU qualification, release authorization, or permission to publish images or release assets. Schema 1 and its public v0.1.1 inputs remain unchanged.

## Build from public successor inputs (schema 3)

Schema 3 supports an explicitly supplied, source-bound public successor packet:

```bash
./scripts/build_images.sh --manifest /absolute/path/public-successor.json
```

This describes builder support, not an available or qualified successor release. The default manifest and consumer pins remain the immutable schema 1/v0.1.1 inputs. No successor archive URL, hash, source pin, or image publication is supplied by this change.

The manifest contains exactly `schema_version`, `version`, `overlay_archive`, `sources`, and `images`:

- `schema_version` is the integer `3`; booleans, floats, and strings are rejected for all schema versions.
- `version` is an explicit `vX.Y.Z` or `vX.Y.Z-rcN`. Each numeric component is a nonnegative decimal integer without leading zeros (except zero itself). Exact `v0.1.1`, `candidate-*`, build metadata, other prerelease forms, and malformed values are rejected.
- `overlay_archive` contains exactly `url`, `filename`, and `sha256`. The URL is credential-free HTTPS without query or fragment and its path basename matches `filename`. The filename starts with an ASCII alphanumeric character, uses only ASCII alphanumerics, dots, underscores, or hyphens, and ends in `.tar.gz` or `.tgz`. SHA-256 is exactly 64 lowercase hexadecimal characters.
- `sources` has the exact schema 2 shape: `GEAK`, `Hyperloom`, and `HaloLoom`, each with exactly `ref` and `tree`, both full lowercase 40-character Git hashes.
- `images` has the same exact four rows, digest-pinned GHCR bases, unique explicit tags, and overlay booleans as schemas 1 and 2. No additional image fields are required.

`--archive` is rejected for both public schemas (1 and 3); it remains required only for schema 2. Schema 3 uses the existing HTTPS downloader with its timeout and redirect checks. The default compressed and unpacked limits are each 1 GiB; `--max-unpacked-bytes` controls both limits for schema 3. There is no mutable-base or local-archive fallback. Duplicate JSON keys, digest mismatch, unsafe extraction, or missing/malformed/mismatched root `candidate-sources.json` fail before **any** Docker action. That JSON object must equal the manifest's `sources` exactly, as in schema 2.

After those gates, schema 3 uses the same fail-closed absence preflight for all four destination tags as schema 2, before committing the stage or pulling/building/tagging. An inspect error is accepted only when it is the exact supported image-not-found response for that tag. This does not reserve tags against concurrent writers. Existing staging paths are refused.

The same Dockerfile and three framework targets build with `--network none` and the exact schema 2 labels: `haloloom.hyperloom_ref`, `haloloom.geak_ref`, `haloloom.haloloom_ref`, `haloloom.candidate_id` (the release `version` for compatibility), and `haloloom.promotion_authority=false`. The AITER row remains a retag of its pinned base, without new source or integration labels. Successful execution prints `HALOLOOM_PUBLIC_BUILD_COMPLETE`; it performs no push and establishes no qualification or promotion authority.

The parent must still complete actual GEAK qualification, prepare and verify the exact offline payload and source/dependency closure, assign the real archive hash and public pins, rebuild and verify runtime identities and physical serving, and complete the authorized publication stages. Updating default consumer inputs follows those gates; this builder change alone does not claim that current or latest images exist or pass.

## Source pins

`manifests/components.json` is authoritative. Public source checkouts can be materialized with:

```bash
python3 scripts/sync_sources.py --root components
```

Every checkout is detached at a full 40-character commit. Existing dirty or wrong-remote destinations are rejected.

The source-current release input binds Hyperloom commit `b91cab3433002fa8381108dd5ea7cb3633b6955e`, tree `67a82a90bf85e54104da833565627354351ebc85`, and wheel SHA-256 `a0229171738133afbdffc91502006e9e872787d5350e7d438c3103064b058d23`; SGLang is `0.5.19.dev0` at `90c62e027831111934a33b9bcc4e533ff61d8526`, not the historical 0.5.15 base. The release archive is 54,043,592 bytes with SHA-256 `1829b58ae16459660e36e091f379131da7983f8d044a7f5fb6a48202d56a6ae5`. The release has exactly three assets: `SHA256SUMS`, that Hyperloom wheel, and `haloloom-v0.1.1-build-inputs.tar.gz`.

## vLLM native Kineto runtime wiring

Native Kineto registration is release wiring for the vLLM lane only. Both the vLLM image and `services.vllm.environment` in `compose.yaml` set exactly:

```text
ROCP_TOOL_LIBRARIES=/opt/venv/lib/python3.14/site-packages/torch/lib/libtorch_cpu.so
LD_LIBRARY_PATH=/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/host-math/lib:/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib
```

The original `ProfileExecutor` inherits these fields without a wrapper or Hyperloom/source/feature change. Default shipped benchmark YAML does not override them. A custom `benchmark.envs` value takes precedence and must match the exact qualified value above. Do not add this wiring to SGLang or Quark.

## Hyperloom wheel dependency contract

The released `hyperloom-inference_optimizer` wheel declares no mandatory base `Requires-Dist` entries. Its requirements are extra-scoped. A normal consumer install uses `[runtime]`, which composes the wheel's `forge`, `llm` and `web` extras plus PyYAML. `pip install --no-deps` is used only when overlaying the exact wheel into an already complete, identity-checked runtime image; it does not make the wheel self-contained.

## Historical v0.1 local-golden recipe (not canonical)

> **Historical reference only.** The sections from here through the legacy layering details document the original local qualified-golden process. They are not inputs or aliases for the canonical public-base rebuild above.

The first release uses the exact physically qualified runtime images as golden inputs:

- vLLM: `hyperloom-vllm-v027-rocm10:v16-runtime-admission-v1`
- SGLang: `hyperloom-sglang-v0515-rocm10:v16-async-v7`
- Quark: `hyperloom-quark-rocm10:gfx1151-v4`

Build the compact server images with:

```bash
docker build -f docker/full-vllm/Dockerfile \
  -t haloloom-vllm-full-gfx1151:v0.1.0 .

docker build -f docker/full-sglang/Dockerfile \
  -t haloloom-sglang-full-gfx1151:v0.1.0 .

docker build -f docker/full-quark-base/Dockerfile \
  -t haloloom-quark-golden-base-gfx1151:v0.1.0 .
```

Each compactor:

1. captures the complete pip freeze and deterministic framework/runtime tree identities;
2. removes only allowlisted non-gfx1151 architecture stores and disposable build/package caches;
3. captures the same identities again;
4. requires byte-identical pre/post runtime identities;
5. copies the already-pruned filesystem into `FROM scratch`.

It does not run pip, replace framework wheels, rebuild source or change the server command. The prune manifest records every removed path, type, byte count and SHA-256.

## Faithful Quark agent overlay

`docker/quark/Dockerfile` starts from the compact golden Quark base. It does not modify `/opt/venv`, Torch, AMD Quark or the original Quark source. Their complete identity is checked before and after.

The reviewed Hyperloom wheel and its Python provider adapters live in a separate `/opt/haloloom-agent` environment. Claude Code, Codex CLI and Hermes are not installed in the image. `docker/quark/plugin-entrypoint` selects a read-only host-agent plug-in and then executes Hyperloom's original `quantization-agent`.

## Final full release layers and optional low-bit ownership

Source ownership and release identity are separate:

https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack

The pack publishes the exact HIP source/HSACO, runtime overlay, vLLM/SGLang patches, source manifests, wheels, tests and physical receipts. HaloLoom pins its release commit/digest in `manifests/components.json`.

Build `docker/full-sglang-release/Dockerfile` from the compact SGLang golden. It installs only the bound pack wheel with `--no-deps`; every pre-existing package-freeze row must remain unchanged.

The v16 vLLM golden contains runtime admission and archived W4A4, but not the final six-route consumer. Build `docker/full-vllm-release/Dockerfile` from its compact dependency closure. It installs only:

- the source-bound full-composition vLLM wheel reconstructed by `adapters/vllm-v16-full.patch` from public upstream commit `4bdc8a788d2e2ce9165d552b3d4d8b72604626bf`;
- the exact pack wheel;
- the pack's async runtime as the active `/opt/hyperloom-runtime` file.

The layer rejects changes to every other package-freeze row and verifies both wheel hashes, the active runtime hash, both vLLM consumer families and `gfx1151`-only framework code objects.

## Turnkey ecosystem layer

`docker/ecosystem/Dockerfile` is the final layer for both framework images. It follows Hyperloom's own container installer split while overriding every moving/default dependency with the release manifest's exact public commits. It installs the faithful Hyperloom wheel and built-in KernelForge, HawgAuto Magpie, IntelliKit Metrix, TraceLens, HawgAuto GEAK, Ray and InferenceX. The complete pinned IntelliKit checkout is retained for optional tools.

External agent CLIs are deliberately not installed. `scripts/detect_agent_plugins.py` discovers an existing host Claude Code, Codex or Hermes installation, and Compose bind-mounts that installation read-only. Provider credentials/configuration remain separate runtime mounts.

### Historical ecosystem-layer reconstruction (not a v0.1.1 path)

`docker/ecosystem/Dockerfile`, the legacy framework Dockerfiles, and `scripts/verify_ecosystem.py` are historical base blueprints. Do not combine the current v0.1.1 wheel with their old source hashes or pins. A fresh clone must use the canonical `./scripts/build_images.sh` path above.

The layer is applied once per framework base. Every build-time gate is fail-closed and recorded in the build log:

- exact component/framework commits fetched with `fetch_exact` and rev-parse checked;
- hash-bound TraceLens compatibility patch (`patches/tracelens/`, SHA-256 in `manifests/components.json`): the pinned TraceLens `a59a9c16` declares `xprof==2.20.1`, which has no Python 3.14 distribution; the patch moves to `xprof==2.20.2` and relaxes the stale `protobuf<7` bound to `<8` because xprof 2.20.2 only requires `protobuf>=3.19.6`. No TraceLens code changes;
- `torch`, `torchvision`, `torchaudio`, `triton`, `grpcio` and `protobuf` are constraint-pinned to whatever the qualified golden base already carries (vLLM base: grpcio 1.78.0 / protobuf 6.33.6; SGLang base: grpcio 1.83.1 / protobuf 7.36.0). The ecosystem layer never re-pins them;
- Hyperloom pins `ray==2.44.1` and `click<8.3`; neither has a Python 3.14 wheel or coexists with the golden Hugging Face Hub. The layer installs `ray[default]==2.55.0` and `click>=8.4.2,<9`, the closest releases that do. Hyperloom's focused Ray suite (137 tests) plus a real local head start/status/stop pass against 2.55.0;
- `scripts/magpie_patch_gate.py` runs Hyperloom's own Magpie/InferenceX script patcher with the same exit policy as Hyperloom's `install.sh`: fatal only on a genuine atomic-copy failure or a live `--concurrent-requests` eval flag. The pinned HawgAuto Magpie already copies scripts atomically and passes `--trust-remote-code` natively, so the legacy trust splice is a benign warning;
- `pip check` must report zero *new* conflicts relative to the golden base (`PIP_CHECK_NO_NEW_CONFLICTS`);
- component checkouts are owned by UID 1000 and registered as exact git `safe.directory` entries so `verify`/`readiness` work under any `HOST_UID`; the build-time `verify_ecosystem.py` runs after that chown so it exercises the non-owner path;
- no `claude`, `codex` or `hermes` binary may resolve inside the image.

### UMA vLLM baseline

On Strix Halo, vLLM's default percentage-based allocator can fail its free-memory snapshot assertion when shared host/GTT memory increases during the profile run. This is not an OOM. Use Hyperloom's existing server-argument seam to provide an explicit KV budget, which skips that unstable inference while retaining the model profile:

```bash
./scripts/haloloom vllm optimize --model <model> --framework vllm \
  --gpu-type radeon8060s \
  --server-args "--kv-cache-memory-bytes <bytes> [--enforce-eager]"
```

The v0.1.1 bounded gate uses 268435456 bytes only for a 512-token, single-request 0.8B canary. Size the budget for the real model, context, and concurrency. Compose also places vLLM, TorchInductor, Triton, and XDG caches under the writable `/workspace` mount and keeps the optional low-bit bridge disabled on normal BF16 routes.

## Deferred clean core flavor

Clean low-bit-free vLLM/SGLang wheels have been built from pinned upstream source and audited for `gfx1151`-only code objects. They are not part of v0.1.0 because neither wheel has passed its own final physical model-serving request.

The failed dependency-reconstruction runtime Dockerfiles and locks are intentionally not published. Local ignored wheel-build experiments remain outside the release tree. A future core release must add new dependency-preserving runtime recipes only after separate physical serving closes.

## Public slim base

`docker/rocm10-gfx1151-base/Dockerfile` provides a digest-pinned public ROCm 10/PyTorch reproducibility base. It is not the source of truth for the first full runtime release; the compact golden images are.

## AITER boundary

AITER tools are optional. AITER attention remains disabled because the tested BF16 Qwen3 GQA2/head-size-128 attention route did not qualify. The supported SGLang serving path uses Triton attention with CUDA graphs disabled.
