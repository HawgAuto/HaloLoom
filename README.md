# HaloLoom

Turnkey Hyperloom for AMD Strix Halo / Radeon 8060S (`gfx1151`, RDNA 3.5) using a pinned ROCm 10 container stack.

One HaloLoom clone installs the complete required Hyperloom workbench. Friends do not assemble Python environments or hunt down companion repositories. HaloLoom detects and mounts an already-installed Claude Code, Codex, or Hermes CLI without installing or copying the agent. For the full `optimize` loop, use a Codex/ChatGPT login, Claude subscription token, or supported OpenAI/Anthropic API credentials. Hermes is a candidate-authoring plug-in, not an Orchestrator transport; a Hermes-only installation still needs separate orchestration credentials.

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

The historical v0.1.0 full images pin that independent pack. SGLang preserves its exact golden framework/runtime bytes. vLLM preserves the compact v16 dependency closure while installing a public-upstream-reconstructible full composition wheel and the pack's async runtime by exact SHA-256. A future core flavor excludes the pack and will be published only after clean framework wheels pass separate physical serving.

## Tested target

| Component | Qualified value |
|---|---|
| GPU | AMD Radeon 8060S |
| Architecture | `gfx1151` |
| Final release qualification host | Ubuntu 24.04.4 LTS, Linux `7.0.0-28-generic` |
| Container ROCm | 10.0.0 |
| Torch | `2.13.0+rocm10.0.0` |
| HIP | `7.15.26333` |
| vLLM | source-built from pinned `0.27.0` development commit |
| SGLang | source-built `0.5.19.dev0` at pinned commit `90c62e027831111934a33b9bcc4e533ff61d8526` |

Other Strix Halo systems should use the same architecture and container userland, but model capacity and throughput still depend on installed RAM, memory speed, thermals and host kernel/driver behavior.

IntelliKit's Metrix package is the required transitive profiling path beneath Magpie and GEAK. The pinned IntelliKit release includes native `gfx1151` device selection, RDNA counter definitions, Strix Halo LPDDR5X accounting and ROCm 10 support. Other IntelliKit packages remain optional source-available tools; they are not required to operate Hyperloom's default loop.

## Prerequisites

- Linux with `/dev/kfd` and `/dev/dri`
- Docker with Compose v2
- user access to the host `video` and `render` groups
- enough RAM and storage for the selected model
- Git and the host's normal Python 3 for the two standard-library setup helpers; no host pip environment
- one existing agent CLI on `PATH`: Claude Code, Codex, or Hermes
- orchestration credentials for `optimize`: Codex/ChatGPT login, Claude subscription token, or supported OpenAI/Anthropic API credentials (a Hermes CLI alone does not provide these)
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

All six low-bit routes retain the direct physical module qualification recorded by the immutable v0.1.0 route artifacts. W4A8 remains the only route with request-owned low-bit dispatch evidence in both frameworks; `qualification/route-status-v0.1.0.json` is the historical low-bit route authority, not the v0.1.1 image-status authority. Ordinary BF16 data-plane and optimizer control-plane evidence from older v0.1.1 lineages remains historical until the source-current final-image smokes close.

| Qualified v0.1.0 route base | Native low-bit route evidence |
|---|---|
| vLLM `sha256:38f60f0b5368eada461c8248fe3b00abdd690565942077e7e1fd9ee0f4b5eb4d` | exact `RDNA35_OK`; 16 layers; 112 async physical dispatches; 7 event completions; zero fallback/foreign rows |
| SGLang `sha256:dbd3b9e61e8df98346ecc33877a9126d2b9854e8d0630ad6be308253b72e97ce` | exact `RDNA35_OK`; 16 layers; 96 async physical dispatches; 6 event completions; zero fallback/foreign rows |

The source-current v0.1.1 build uses Hyperloom commit `b91cab3433002fa8381108dd5ea7cb3633b6955e`, tree `67a82a90bf85e54104da833565627354351ebc85`, and wheel SHA-256 `a0229171738133afbdffc91502006e9e872787d5350e7d438c3103064b058d23`. [The final runtime closeout](qualification/receipts/release-closeout-v0.1.1.json) and `manifests/components.json` bind the exact final images, completed physical checks, and anonymous OCI index/manifest/config readback. vLLM completed the original 16-request 128/128 profile action with 128,912 physical GPU kernels and 193,713 HIP runtime events. SGLang and Quark each completed their unchanged five-request model-runtime canary; those are city-substring checks, not new low-bit-route, exact-format, or quality qualification. The four final HIP/Triton toolchain paths passed no-device compilation. Existing `*-final-v0.1.1.json` files and v0.1.0 W4A8 dispatch receipts remain historical lineage evidence, not new-image route claims. The runtime closeout is a pre-source-publication snapshot; source/tag and anonymous installation verification are separate release checks.

Public registry digests are recorded in `manifests/components.json` after push/readback verification.

The historical Quark lineage preserves a real INT8 PTQ/export lifecycle, but its candidate is **REJECTED**: the bundled-source evaluation scored 4/16 examples versus 3/16 for the quantized output, a 25% relative gap that exceeds the 3% limit. This proves lifecycle function only; it supports no quality or performance claim. The source-current Quark image passed its final five-request runtime canary and bundles no agent CLI; that serving result does not change the rejected candidate’s quality classification.

The optional AITER tools image's exact published identity is recorded in `manifests/components.json`. Historical evidence covers native gfx1151 device import, `module_aiter_core` JIT/load, gemm-common operation/JIT, and RMSNorm operation/numerical/JIT. `module_sample` compiles and loads, but greedy sampling fails the exact argmax oracle and is unavailable. AITER attention also remains unavailable; the supported SGLang attention route is Triton.

The default installer performs native-gfx1151 preflight, detects one existing host agent CLI, writes only non-secret plug-in paths to `.env`, and pulls the full vLLM, full SGLang and Quark images. It performs no host `pip install`. Use `--include-aiter` for the optional AITER image or `--sync-sources` to materialize separate pinned source checkouts for development.

All GPU services pin `/opt/rocm/core-10.0` and its matching library directories. Keep the supplied vLLM native-profiler dependency closure and both SGLang cache variables from Compose; `SGLANG_CACHE_DIR` and `SGLANG_JIT_CACHE_DIR` are independent and must point into the writable workspace. Do not prepend the image's duplicate modular-SDK library roots or set `HSA_OVERRIDE_GFX_VERSION`; doing so invalidates the qualified runtime closure. SGLang low-bit dispatch remains opt-in (`HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1` plus an exact supported `--quantization` value); the default BF16 route keeps it disabled.

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

### End-to-end on a fresh Strix Halo box

Everything below runs inside the pulled images. The host needs Docker, the `amdgpu` kernel driver, `video`/`render` group membership, Git, standard-library Python 3, one agent CLI, and the orchestration credentials described below.

```bash
# 1. Prove the pulled image is exactly the pinned ecosystem (sources, wheel, imports).
./scripts/haloloom vllm verify

# 2. Prove your host agent CLI is reachable inside the container (read-only mount).
./scripts/haloloom vllm agent-check           # prints e.g. "codex-cli 0.151.0"

# 3. Create the Hyperloom readiness epoch in ./workspace (once per workspace),
#    then inspect it. Status before initialize exits 2 with instructions.
./scripts/haloloom vllm readiness initialize
./scripts/haloloom vllm readiness status      # "healthy": true, 23 targets, no fallback

# 4. (Optional) Quantize with Quark via Hyperloom's quantization-agent.
python3 scripts/quantize.py --workspace my-quant --model-id <agent-model-id> \
  --prompt 'Quantize /workspace/models/<model> with W8A8 and preserve lm_head.'

# 5. Run Hyperloom's optimizer against the framework of your choice.
#    Credentials are upstream Hyperloom's, unchanged (see "Credentials" below).
#    Your selected CLI authors KernelForge/GEAK candidates via its read-only
#    host plug-in. The wrapper forwards credential NAMES, never values.
./scripts/haloloom vllm optimize --help
./scripts/haloloom vllm optimize --model <hf-model-id> --framework vllm \
  --gpu-type radeon8060s

# 6. Serve. Hyperloom's final report (reports/final.json) records the exact
#    extra_server_args / extra_envs of the accepted configuration; pass them
#    to the serving helper yourself (HaloLoom does not auto-apply results).
python3 scripts/serve.py vllm <hf-model-id> --model-revision <sha> [-- <extra args>]
```

Kernel candidates the optimizer proposes are compiled *inside* the image: `hipcc --offload-arch=gfx1151`, `torch.utils.cpp_extension` and Triton JIT are all present and physically smoke-tested on gfx1151 (`qualification/receipts/*-ecosystem-layer-v0.1.0.json`, `gpu_build_smoke`). No ROCm, Torch or compiler is required on the host.

## Credentials

HaloLoom preserves upstream's API-key and Claude subscription paths and adds the Codex `native_oauth` transport described below. `./scripts/haloloom` forwards credential variable names from your shell with Compose's name-only `-e NAME` form, keeping values out of argv, `.env`, Compose YAML and this repository. The resulting container environment still contains the values and is readable through container inspection by users with Docker/administrator access; child tools may also log them. See `SECURITY.md`.

| You have | Orchestrator (`optimize` loop) | Candidate authoring (KernelForge/GEAK) |
|---|---|---|
| Claude Max/Pro subscription | `claude setup-token` → `export CLAUDE_CODE_OAUTH_TOKEN=...` (upstream option 4) | same token via the mounted Claude CLI |
| Anthropic API key | `export ANTHROPIC_API_KEY=...` | same |
| OpenAI API key | `export OPENAI_API_KEY=...` (add `OPENAI_BASE_URL` for a gateway) | same, or `codex login --api-key` |
| ChatGPT/Codex subscription | `codex login` on the host. When `~/.codex/auth.json` exists and no `OPENAI_API_KEY`/`OPENAI_BASE_URL` is set, the workbench selects Hyperloom's Codex `native_oauth` mode for **every** OpenAI-side role — Orchestrator, critic review, robustness RCA, framework specialist, proposal scorer, framework audit (HaloLoom-added; mirrors upstream's own Claude-subscription transport, `claude_oneshot`). No key, no proxy, no mocks. | `codex login` → mounted `~/.codex` (KernelForge `native_oauth`) |

Hermes remains an available candidate-authoring arm (`--agent hermes`, qualified in the readiness epoch); it is not an Orchestrator transport.

`native_oauth` is the only credential-path change HaloLoom carries relative to upstream Hyperloom, and it is built the way upstream already solved the same problem for Claude subscriptions. Upstream's `claude_oneshot.py` drives single-shot Claude calls through the Claude CLI behind the Anthropic-client shape when the credential is a subscription token; HaloLoom's `codex_oneshot.py` is its OpenAI-side twin, returned by upstream's own `get_openai_client()`/`get_async_openai_client()` seam, so critic, robustness, scorer and audit code is untouched. The Orchestrator's and specialist's existing `CodexSession` gains the same `auth_mode` KernelForge's Codex backend already has (no `model_providers` override, the operator's own `CODEX_HOME` owns the login, gateway variables scrubbed from the child). Default users are byte-identical to upstream. It is opt-in via `INFERENCE_OPTIMIZER_CODEX_AUTH_MODE=native_oauth` + `INFERENCE_OPTIMIZER_CODEX_HOME`; any API key/base URL set alongside it is a fatal preflight error, never a silent fallback. Deterministic benchmark, build, correctness, acceptance/rejection and cleanup gates are provider-independent and unchanged.

## Strix Halo control-plane footguns

These are configuration boundaries found by the v0.1.1 end-to-end gate, not optional tuning folklore:

- **Do not set `--tick-interval-sec 0` for a bounded real run.** The Coordinator can consume the tick limit while an asynchronous PRELUDE task is still in flight. Use `--tick-interval-sec 1` (or longer) and a tick budget large enough for model startup and benchmarking.
- **The workbench container is Codex's external sandbox.** It has no bubblewrap, so the Codex login path sets `HYPERLOOM_CODEX_EXTERNAL_SANDBOX=1`, `HYPERLOOM_CODEX_SANDBOX_MODE=bypass`, and `GEAK_CODEX_EXTERNAL_SANDBOX=1`. Do not remove those while using the container; each role's Hyperloom/KernelForge writable-root allowlist still applies.
- **Mutable caches belong in `/workspace`.** Compose sets `VLLM_CACHE_ROOT=/workspace/.cache/vllm` together with `XDG_CACHE_HOME`, `VLLM_CONFIG_ROOT`, `TORCHINDUCTOR_CACHE_DIR`, and `TRITON_CACHE_DIR`. The parent of the read-only Hugging Face bind mount under `/home/haloloom/.cache` can be root-owned and is not a safe cache root for a non-root worker.
- **Normal BF16 routes keep the optional low-bit bridge off.** Both services set `HYPERLOOM_GFX1151_LOWBIT_BRIDGE="0"`. With `scripts/serve.py`, supply `--model-revision <sha>` before the `--` separator and `--quantization <supported-gfx1151-format>` after it to enable the bridge for that exact low-bit route; there is no `--lowbit` flag. Enabling the bridge for an ordinary BF16 request can select an adapter that is not part of that route.
- **vLLM's percentage memory profiler assumes a stable discrete-GPU free-memory snapshot.** On UMA, harmless host/GTT release can make free memory increase during profiling and trip that assertion. For a bounded gate, use an explicit budget such as `--server-args "--kv-cache-memory-bytes 268435456 --enforce-eager"`. For real models, size `--kv-cache-memory-bytes` for the intended context/concurrency rather than copying the 256 MiB smoke value.
- **Native Kineto registration is vLLM-only.** The vLLM image and `services.vllm.environment` in Compose set exactly `ROCP_TOOL_LIBRARIES=/opt/venv/lib/python3.14/site-packages/torch/lib/libtorch_cpu.so` and `LD_LIBRARY_PATH=/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/host-math/lib:/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib`. The original `ProfileExecutor` inherits these values. A custom `benchmark.envs` entry overrides inheritance and must repeat the exact qualified value. This changes no Hyperloom source, wrapper, profiler feature or schedule.

## Quark

The Quark image uses Hyperloom's original `quantization-agent` entrypoint and original skill/workspace/retry/validation contract:

```bash
python3 scripts/quantize.py \
  --workspace qwen-w8a8 \
  --model-id <agent-model-id> \
  --prompt 'Quantize the model at /workspace/models/Qwen3-0.6B with W8A8 and preserve lm_head.'
```

`--model-id` selects the **agent's** model (for example, the model available through your Codex subscription), not the Hugging Face model to quantize. Specify the target model path or ID in `--prompt`. Claude, Codex and Hermes remain peer transports. The prompt and model ID are command-line/loggable inputs; do not put secrets in either. Quark output quality/evaluation status is reported by the original validators; an unavailable offline evaluation environment is not rewritten as quantization failure.

## AITER boundary

The optional AITER tools image includes the source-bound wheel from AITER commit `a343a105…`. Physical gfx1151 evidence covers package installation, device import and several JIT modules. AITER attention and sampling are unavailable. The supported SGLang serving path uses default Triton attention with CUDA graphs disabled. The reviewed TraceLens 0.5.19 patch payload is strict, CPU-replayable and idempotent; graph-shape discovery, graph capture/replay and EAGLE runtime are not qualified, so no graph claim is made.

## Reproducibility

- public source commits are pinned by full SHA
- base images are pinned by digest
- framework source trees have recursive SHA-256 manifests
- framework wheels are audited for `gfx1151`-only code objects
- release assets and images have checksums/digests
- image pruning touches only allowlisted architecture stores and records every removed path/hash/byte count
- v0.1 full images bind the qualified low-bit closure to its independent source repository and exact release-wheel hashes
- clean low-bit-free wheels remain provenance-bound but are not release images until separately qualified by physical serving

The v0.1.1 release has exactly three assets: `SHA256SUMS`, the current Hyperloom wheel, and `haloloom-v0.1.1-build-inputs.tar.gz` (54,043,592 bytes; SHA-256 `1829b58ae16459660e36e091f379131da7983f8d044a7f5fb6a48202d56a6ae5`). Use `./scripts/build_images.sh`; exact final image and registry identities belong only in `manifests/components.json` and `qualification/receipts/release-closeout-v0.1.1.json` after verification.

See `docs/BUILD.md`, `docs/QUALIFICATION.md`, `NOTICE.md` and `SECURITY.md`.

## No production activation

HaloLoom prepares and validates isolated runtime lanes. It does not automatically replace existing inference services, modify production model registries or promote optimizer candidates.
