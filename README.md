# HaloLoom

Turnkey Hyperloom for AMD Strix Halo / Radeon 8060S (`gfx1151`, RDNA 3.5) using a pinned ROCm 10 container stack.

One HaloLoom clone installs the complete required Hyperloom workbench. Friends do not assemble Python environments or hunt down companion repositories. The only external agent requirement is one already-installed Claude Code, Codex, or Hermes CLI; HaloLoom detects it and mounts that existing installation into the workbench without installing or copying the agent.

## What ships

- faithful Hyperloom source and wheel, including built-in KernelForge
- HawgAuto Magpie Radeon/gfx1151 benchmark and trace runners
- AMD TraceLens trace analysis
- HawgAuto GEAK gfx1151 and provider-neutral workflow port
- IntelliKit Metrix with native gfx1151/Strix Halo counters and ROCm 10 support
- the full pinned IntelliKit source checkout for optional specialist tools
- InferenceX benchmark and accuracy harness
- the independently released six-route Strix Halo low-bit kernel pack
- `haloloom-vllm-full-gfx1151`: qualified vLLM runtime plus the complete workbench
- `haloloom-sglang-full-gfx1151`: qualified SGLang runtime plus the complete workbench
- `haloloom-quark-rocm10-gfx1151`: original skill-driven Quark workflow with host-agent plug-in support
- `haloloom-aiter-tools-full-gfx1151`: optional AITER tools/JIT image; not required for ordinary use

Every required source is pinned by full commit in `manifests/components.json`. Magpie, IntelliKit Metrix, TraceLens, GEAK, InferenceX, Hyperloom and KernelForge are installed in both framework workbench images. The external agent CLIs themselves are deliberately not bundled.

Exact commits, image digests and checksums are in `manifests/components.json` and the release checksum manifest.

### Low-bit kernels are a separate package

The optional six-route gfx1151 low-bit module and its vLLM/SGLang consumers are independently versioned at:

https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack

The v0.1 full images pin that independent pack. SGLang preserves its exact golden framework/runtime bytes. vLLM preserves the compact v16 dependency closure while installing a public-upstream-reconstructible full composition wheel and the pack's async runtime by exact SHA-256. A future core flavor excludes the pack and will be published only after clean framework wheels pass separate physical serving.

## Tested target

| Component | Qualified value |
|---|---|
| GPU | AMD Radeon 8060S |
| Architecture | `gfx1151` |
| Host | Ubuntu 24.04, Linux 6.17 |
| Container ROCm | 10.0.0 |
| Torch | `2.13.0+rocm10.0.0` |
| HIP | `7.15.26333` |
| vLLM | source-built from pinned `0.27.0` development commit |
| SGLang | pinned `0.5.15` release commit |

Other Strix Halo systems should use the same architecture and container userland, but model capacity and throughput still depend on installed RAM, memory speed, thermals and host kernel/driver behavior.

IntelliKit's Metrix package is the required transitive profiling path beneath Magpie and GEAK. The pinned IntelliKit release includes native `gfx1151` device selection, RDNA counter definitions, Strix Halo LPDDR5X accounting and ROCm 10 support. Other IntelliKit packages remain optional source-available tools; they are not required to operate Hyperloom's default loop.

## Prerequisites

- Linux with `/dev/kfd` and `/dev/dri`
- Docker with Compose v2
- user access to the host `video` and `render` groups
- enough RAM and storage for the selected model
- Git and the host's normal Python 3 for the two standard-library setup helpers; no host pip environment
- one existing agent CLI on `PATH`: Claude Code, Codex, or Hermes
- no `HSA_OVERRIDE_GFX_VERSION`; native gfx1151 is required

HaloLoom never stops unrelated GPU jobs automatically. Launch helpers acquire `/run/lock/hermes-vllm-gfx1151.lock` and fail if `/dev/kfd` is already owned.

## Quickstart

```bash
git clone https://github.com/HawgAuto/HaloLoom.git
cd HaloLoom

unset HSA_OVERRIDE_GFX_VERSION
./scripts/install.sh

# Prove the complete in-image ecosystem and exact source pins.
./scripts/haloloom vllm verify

# Show Hyperloom's optimizer commands from the vLLM or SGLang workbench.
./scripts/haloloom vllm --help
./scripts/haloloom sglang optimize --help

# Start one real server in the foreground while holding the shared GPU lock.
python3 scripts/serve.py vllm Qwen/Qwen3-0.6B \
  --model-revision c1899de289a04d12100db370d81485cdf75e47ca
# Or:
python3 scripts/serve.py sglang Qwen/Qwen3-0.6B \
  --model-revision c1899de289a04d12100db370d81485cdf75e47ca
```

For the locally qualified W4A8 reference route, supply the exact model revision before `--` and pass framework arguments after it:

```bash
python3 scripts/serve.py vllm Qwen/Qwen3.5-0.8B \
  --model-revision 2fc06364715b967f1860aea9cf38778875588b17 \
  --max-model-len 2048 -- --quantization gfx1151-w4a8

python3 scripts/serve.py sglang Qwen/Qwen3.5-0.8B \
  --model-revision 2fc06364715b967f1860aea9cf38778875588b17 \
  --max-model-len 2048 -- --quantization gfx1151-w4a8
```

These routes are correctness/dispatch references, not claimed performance wins.

All six routes pass direct physical module qualification. Only W4A8 has fresh final-image vLLM and SGLang request evidence in this release; the other five remain direct-only at the framework boundary. `qualification/route-status-v0.1.0.json` is the current status authority. Historical `HOLD` text inside immutable route-spec inputs describes their pre-run state and is retained because the successful receipts bind those exact files.

| Qualified golden base (route evidence) | Native route evidence | Published image = golden + ecosystem layer |
|---|---|---|
| vLLM `sha256:38f60f0b5368eada461c8248fe3b00abdd690565942077e7e1fd9ee0f4b5eb4d` | exact `RDNA35_OK`; 16 layers; 112 async physical dispatches; 7 event completions; zero fallback/foreign rows | `sha256:0835d9d2782edc480dbbcb5ddb4dbd1d696d6e3038f4b23c761855bd5f1fa30c` |
| SGLang `sha256:dbd3b9e61e8df98346ecc33877a9126d2b9854e8d0630ad6be308253b72e97ce` | exact `RDNA35_OK`; 16 layers; 96 async physical dispatches; 6 event completions; zero fallback/foreign rows | `sha256:cd66db5627fa5fab16fe276cf2804c7eaa2a6a1310f48e3963321d7a34ba1259` |

The published images add the pinned Hyperloom/Magpie/Metrix/TraceLens/GEAK/InferenceX/Ray layer on top of the exact golden base. Each has an ecosystem-layer receipt (`qualification/receipts/*-ecosystem-layer-v0.1.0.json`) proving the golden runtime identity, low-bit runtime and device path are unchanged: byte-identical low-bit module digest, base `torch`/`grpcio`/`protobuf` pins preserved, zero new `pip check` conflicts, sealed readiness files byte-identical, no agent CLI bundled, and a bounded native `gfx1151` smoke under the exclusive GPU lock (Torch device/tensor op, framework parser on ROCm, readiness controller). Model-serving route evidence is owned by the golden receipts; the layer receipt does not re-claim it.

Public registry digests are recorded in `manifests/components.json` after push/readback verification.

Quark final image `sha256:99dbc478ca7d8a2af6eb973f625e62d5b477f9261efc7d1896aba1596cb9b1d3` passes physical gfx1151 execution through the final public-source Hyperloom wheel while retaining byte-identical golden Quark/Torch/source identity. It bundles no agent CLI. Its successor receipt binds the prior real INT8 PTQ/export lifecycle, whose candidate was correctly rejected on quality. No fresh provider call, plan generation or PTQ export was run for the final image, and no quality win is claimed.

AITER tools image `sha256:a66c94bdbb877205fa125788be1e1d7ae5b03bd1e18b3c846298ddc97af3850c` passes native gfx1151 device import, `module_aiter_core` JIT/load, gemm-common operation/JIT, and RMSNorm operation/numerical/JIT. `module_sample` compiles and loads, but its greedy-sample operation fails the exact argmax oracle and is unavailable. AITER attention also remains unavailable; the supported SGLang attention route is Triton.

The default installer performs native-gfx1151 preflight, detects one existing host agent CLI, writes only non-secret plug-in paths to `.env`, and pulls the full vLLM, full SGLang and Quark images. It performs no host `pip install`. Use `--include-aiter` for the optional AITER image or `--sync-sources` to materialize separate pinned source checkouts for development.

All GPU services pin `/opt/rocm/core-10.0` and its matching library directories. Do not prepend the image's duplicate modular-SDK library roots or set `HSA_OVERRIDE_GFX_VERSION`; doing so invalidates the qualified runtime closure. SGLang low-bit dispatch remains opt-in (`HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1` plus an exact supported `--quantization` value); the default BF16 route keeps it disabled.

In another terminal:

```bash
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen/Qwen3-0.6B",
    "messages": [{"role": "user", "content": "Reply with exactly HALOLOOM_OK"}],
    "max_tokens": 16,
    "temperature": 0
  }'
```

The first run downloads model weights into the configured Hugging Face cache. Credentials are never baked into images or manifests.

## Hyperloom workbench and agent plug-in

Hyperloom runs inside the selected non-root framework workbench, beside the exact ROCm/Torch/framework environment it profiles and changes. No host Docker socket is mounted. `./scripts/haloloom` launches the workbench and holds the shared gfx1151 GPU lease for the optimizer lifecycle.

`./scripts/install.sh --agent auto` prefers the provider arms qualified by the final readiness epoch: Codex, then Hermes, then the available-but-not-yet-readiness-qualified Claude wiring. An exact choice is also supported:

```bash
./scripts/install.sh --agent codex
./scripts/haloloom vllm --help
```

The selected installation root is bind-mounted read-only at its original absolute path so Node-based Codex and Python-environment Hermes installations keep their own dependency closure. Its existing auth/config home is mounted separately into `/home/haloloom`. HaloLoom never bakes an agent executable or credential into an image.

## Quark

The Quark image uses Hyperloom's original `quantization-agent` entrypoint and original skill/workspace/retry/validation contract:

```bash
python3 scripts/quantize.py \
  --workspace qwen-w8a8 \
  --model-id <your-model-id> \
  --prompt 'Quantize the model at /workspace/models/Qwen3-0.6B with W8A8 and preserve lm_head.'
```

Claude, Codex and Hermes remain peer transports. Quark output quality/evaluation status is reported by the original validators; an unavailable offline evaluation environment is not rewritten as quantization failure.

## AITER boundary

The optional AITER tools image includes the source-bound wheel from AITER commit `a343a105…`. Physical gfx1151 evidence covers package installation, device import and several JIT modules. AITER attention is disabled by default because the tested BF16 Qwen3 GQA2/head-size-128 geometry did not qualify. The supported SGLang serving path uses Triton attention with CUDA graphs disabled.

## Reproducibility

- public source commits are pinned by full SHA
- base images are pinned by digest
- framework source trees have recursive SHA-256 manifests
- framework wheels are audited for `gfx1151`-only code objects
- release assets and images have checksums/digests
- image pruning touches only allowlisted architecture stores and records every removed path/hash/byte count
- v0.1 full images bind the qualified low-bit closure to its independent source repository and exact release-wheel hashes
- clean low-bit-free wheels remain provenance-bound but are not release images until separately qualified by physical serving

See `docs/BUILD.md`, `docs/QUALIFICATION.md`, `NOTICE.md` and `SECURITY.md`.

## No production activation

HaloLoom prepares and validates isolated runtime lanes. It does not automatically replace existing inference services, modify production model registries or promote optimizer candidates.
