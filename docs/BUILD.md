# Building HaloLoom

## Normal users

Normal users pull the released images with `scripts/install.sh`. They do not rebuild ROCm, vLLM, SGLang or Quark.

## Source pins

`manifests/components.json` is authoritative. Public source checkouts can be materialized with:

```bash
python3 scripts/sync_sources.py --root components
```

Every checkout is detached at a full 40-character commit. Existing dirty or wrong-remote destinations are rejected.

## Hyperloom wheel dependency contract

The released `hyperloom-inference_optimizer` wheel declares no mandatory base `Requires-Dist` entries. Its requirements are extra-scoped. A normal consumer install uses `[runtime]`, which composes the wheel's `forge`, `llm` and `web` extras plus PyYAML. `pip install --no-deps` is used only when overlaying the exact wheel into an already complete, identity-checked runtime image; it does not make the wheel self-contained.

## Canonical v0.1 images: compact the qualified goldens

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

### Rebuilding the ecosystem layer yourself

`dist/` is not tracked. Before `docker build -f docker/ecosystem/Dockerfile`, place the exact released wheel at `dist/hyperloom/hyperloom_inference_optimizer-1.0.0-py3-none-any.whl` and verify it against `release/SHA256SUMS` (the Dockerfile re-checks the hash and fails closed on mismatch):

```bash
mkdir -p dist/hyperloom
gh release download v0.1.0 --repo HawgAuto/HaloLoom \
  --pattern 'hyperloom_inference_optimizer-1.0.0-py3-none-any.whl' --dir dist/hyperloom
(cd dist/hyperloom && sha256sum --check --strict ../../release/SHA256SUMS)
docker build --build-arg BASE_IMAGE=<qualified vllm or sglang golden> \
  -f docker/ecosystem/Dockerfile -t <tag> .
```

The layer is applied once per framework base. Every build-time gate is fail-closed and recorded in the build log:

- exact component/framework commits fetched with `fetch_exact` and rev-parse checked;
- hash-bound TraceLens compatibility patch (`patches/tracelens/`, SHA-256 in `manifests/components.json`): the pinned TraceLens `a59a9c16` declares `xprof==2.20.1`, which has no Python 3.14 distribution; the patch moves to `xprof==2.20.2` and relaxes the stale `protobuf<7` bound to `<8` because xprof 2.20.2 only requires `protobuf>=3.19.6`. No TraceLens code changes;
- `torch`, `torchvision`, `torchaudio`, `triton`, `grpcio` and `protobuf` are constraint-pinned to whatever the qualified golden base already carries (vLLM base: grpcio 1.78.0 / protobuf 6.33.6; SGLang base: grpcio 1.83.1 / protobuf 7.36.0). The ecosystem layer never re-pins them;
- Hyperloom pins `ray==2.44.1` and `click<8.3`; neither has a Python 3.14 wheel or coexists with the golden Hugging Face Hub. The layer installs `ray[default]==2.55.0` and `click>=8.4.2,<9`, the closest releases that do. Hyperloom's focused Ray suite (137 tests) plus a real local head start/status/stop pass against 2.55.0;
- `scripts/magpie_patch_gate.py` runs Hyperloom's own Magpie/InferenceX script patcher with the same exit policy as Hyperloom's `install.sh`: fatal only on a genuine atomic-copy failure or a live `--concurrent-requests` eval flag. The pinned HawgAuto Magpie already copies scripts atomically and passes `--trust-remote-code` natively, so the legacy trust splice is a benign warning;
- `pip check` must report zero *new* conflicts relative to the golden base (`PIP_CHECK_NO_NEW_CONFLICTS`);
- component checkouts are owned by UID 1000 and registered as exact git `safe.directory` entries so `verify`/`readiness` work under any `HOST_UID`; the build-time `verify_ecosystem.py` runs after that chown so it exercises the non-owner path;
- no `claude`, `codex` or `hermes` binary may resolve inside the image.

## Deferred clean core flavor

Clean low-bit-free vLLM/SGLang wheels have been built from pinned upstream source and audited for `gfx1151`-only code objects. They are not part of v0.1.0 because neither wheel has passed its own final physical model-serving request.

The failed dependency-reconstruction runtime Dockerfiles and locks are intentionally not published. Local ignored wheel-build experiments remain outside the release tree. A future core release must add new dependency-preserving runtime recipes only after separate physical serving closes.

## Public slim base

`docker/rocm10-gfx1151-base/Dockerfile` provides a digest-pinned public ROCm 10/PyTorch reproducibility base. It is not the source of truth for the first full runtime release; the compact golden images are.

## AITER boundary

AITER tools are optional. AITER attention remains disabled because the tested BF16 Qwen3 GQA2/head-size-128 attention route did not qualify. The supported SGLang serving path uses Triton attention with CUDA graphs disabled.
