# HaloLoom

**Serve, quantize, profile, and optimize LLMs on AMD Strix Halo.**

HaloLoom packages [Hyperloom](https://github.com/AMD-AGI/Hyperloom) and its supporting tools into a pinned ROCm 10 Docker environment for the Radeon 8060S (`gfx1151`, RDNA 3.5). It brings vLLM, SGLang, AMD Quark, GPU profiling, and agent-assisted kernel optimization into one repository.

The goal is to make this stack usable without assembling several projects, resolving conflicting Python dependencies, or building a host ROCm development environment. Install the released images, connect your existing agent CLI, and run the workflow you need. Model weights are downloaded separately.

[Get started](#quickstart) · [User guide](docs/USAGE.md) · [Build from public inputs](docs/BUILD.md) · [Test results and limitations](docs/QUALIFICATION.md) · [Releases](https://github.com/HawgAuto/HaloLoom/releases)

## What's included

| Tool | What it does |
|---|---|
| **vLLM and SGLang** | Serve models through OpenAI-compatible APIs, with the optimization tools installed beside each framework. |
| **Hyperloom** | Coordinates profiling, candidate generation, testing, and inference optimization. |
| **AMD Quark** | Quantizes models through Hyperloom's agent-assisted quantization workflow. |
| **KernelForge and GEAK** | Generate, compile, and test GPU-kernel candidates. |
| **Magpie and InferenceX** | Run inference benchmarks and accuracy checks. |
| **TraceLens and IntelliKit Metrix** | Analyze traces and collect GPU profiling data with gfx1151 support. |
| **AITER tools (optional)** | Provide selected kernel-development and JIT tools; not required for normal serving. |

The default installer pulls the vLLM, SGLang, and Quark images. The framework images include the workbench and pinned component sources; the full IntelliKit source is also available for its optional tools. HIP and Triton compilation run inside the containers.

Claude Code, Codex, and Hermes are supported as **existing host CLI plug-ins**, not bundled agents. The optional [Strix Halo Low-bit Kernel Pack](https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack) is independently versioned; its use and test coverage are described in the [user guide](docs/USAGE.md#optional-low-bit-kernels).

## Requirements

- An AMD Strix Halo system with a Radeon 8060S / native `gfx1151` GPU.
- Linux with a working `amdgpu` driver, `/dev/kfd`, and `/dev/dri`.
- Docker with Compose v2, permission to use Docker, and access to the `video` and `render` groups.
- Git, the host's normal Python 3, and enough RAM and disk space for the images and selected model.
- An installed Claude Code, Codex, or Hermes CLI on `PATH`.
- For the full optimizer: a Codex/ChatGPT login, Claude subscription token, or supported OpenAI/Anthropic API credentials. **Hermes can author candidates but does not supply the optimizer's orchestration credentials.** See [authentication](docs/USAGE.md#authentication).

The tested host used Ubuntu 24.04.4 LTS and Linux `7.0.0-28-generic`. The containers supply ROCm 10, Torch, the frameworks, and build tools. You do not need a host Python package environment or host ROCm compiler. The installer does **not** install Docker, the kernel driver, or an agent CLI.

Keep `HSA_OVERRIDE_GFX_VERSION` unset. Capacity and speed depend on your RAM, model, context length, concurrency, cooling, and host driver.

## Quickstart

### 1. Install and check the workbench

```bash
git clone https://github.com/HawgAuto/HaloLoom.git
cd HaloLoom

unset HSA_OVERRIDE_GFX_VERSION
./scripts/install.sh
./scripts/haloloom vllm verify
./scripts/haloloom vllm agent-check
```

To choose a CLI explicitly, use `./scripts/install.sh --agent codex` (or `claude` / `hermes`). Add `--include-aiter` only if you need the optional tools image. No host `pip install` is performed.

**v0.1.2 installer correction:** use current `main` or the `v0.1.2-installer.1` source tag. The original `v0.1.2` source tag selected v0.1.1 images by mistake and is preserved unchanged. The corrected installer reads the release from `manifests/components.json` and uses the already-published v0.1.2 images; no image rebuild is needed. For an existing checkout, switch to the corrected source and rerun `./scripts/install.sh`.


### 2. Start a small text model

This example uses Qwen3.5-0.8B with a short context and an explicit KV-cache budget, avoiding vLLM's percentage-based memory sizing on shared-memory hardware:

```bash
python3 scripts/serve.py vllm Qwen/Qwen3.5-0.8B \
  --model-revision 2fc06364715b967f1860aea9cf38778875588b17 \
  --max-model-len 512 -- \
  --enforce-eager --gpu-memory-utilization 0.10 \
  --max-num-seqs 1 --max-num-batched-tokens 128 \
  --kv-cache-memory-bytes 268435456 --language-model-only \
  --dtype bfloat16 --attention-backend TRITON_ATTN \
  --safetensors-load-strategy eager --host 0.0.0.0 --port 8000
```

The first run downloads the model into the configured Hugging Face cache. The helper runs the server in the foreground; stop it with **Ctrl+C**. This is a small text-only starting configuration, not a memory budget for larger models or long contexts.

**Network access:** the supplied Compose configuration publishes port 8000 on the host's interfaces, without API authentication by default. Restrict access to trusted clients or [bind the port to loopback](docs/USAGE.md#network-and-model-security) before running it. The serving helpers enable model-provided code, so use model sources you trust.

For SGLang, use `python3 scripts/serve.py sglang` with a model ID and revision; the [user guide](docs/USAGE.md#serve-with-sglang) has a complete example. Run one GPU workload at a time. HaloLoom's helpers share a GPU lock and never stop unrelated jobs automatically.

### 3. Send a request

Once the server is ready, run this in another terminal:

```bash
curl -sS http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "Qwen/Qwen3.5-0.8B",
    "messages": [{"role": "user", "content": "What is the capital of France?"}],
    "max_tokens": 32,
    "temperature": 0,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

## Quantize and optimize

Stop the serving process before starting GPU work in another tool. Set up your [authentication](docs/USAGE.md#authentication), then initialize the optimizer workspace:

```bash
./scripts/haloloom vllm readiness initialize
./scripts/haloloom vllm readiness status
./scripts/haloloom vllm optimize --help
```

To optimize a model, replace `<hf-model-id>` with its Hugging Face ID:

```bash
./scripts/haloloom vllm optimize --model <hf-model-id> --framework vllm \
  --gpu-type radeon8060s
```

Use the SGLang workbench and `--framework sglang` for SGLang. The [user guide](docs/USAGE.md#optimize-a-model) covers memory sizing and applying results. HaloLoom does not automatically apply optimized settings or replace existing inference services.

For quantization, `python3 scripts/quantize.py` runs the Quark workflow. Its `--model-id` selects the **agent's model**; the model to quantize belongs in `--prompt`. See the [Quark example](docs/USAGE.md#quantize-with-quark). Evaluate the output on your workload before serving it; quantization and optimization do not guarantee a quality or speed improvement.

## Support and practical limits

- **vLLM:** the published small-model API check used a fixed KV-cache budget and text-only operation. Automatic shared-memory sizing can fail when host memory changes during profiling; broad multimodal coverage is not established by that check.
- **SGLang:** use the supplied Triton attention configuration with CUDA graphs disabled. Graph discovery, capture/replay, and EAGLE operation are not supported by the current test evidence.
- **AITER:** attention and sampling are unavailable in this release. The optional tools image is not an alternative default serving backend.
- **Low-bit kernels:** support is specific to the format, framework, model, and image tested. See the [recorded coverage](docs/QUALIFICATION.md), rather than assuming every included route is tested on every release image.

<details>
<summary>Advanced configuration notes</summary>

### Strix Halo control-plane footguns

These notes apply when changing optimizer or container settings; normal users should keep the supplied defaults.

- **Optimizer timing:** if you set a tick interval, use `--tick-interval-sec 1` or longer, not zero. A zero interval can exhaust a tick budget before asynchronous model startup finishes.
- **Codex sandbox:** the workbench uses Docker as its external sandbox and sets `HYPERLOOM_CODEX_EXTERNAL_SANDBOX=1` and `HYPERLOOM_CODEX_SANDBOX_MODE=bypass`. Keep these settings and the existing writable-root restrictions together; see [security](SECURITY.md).
- **Writable caches:** keep `VLLM_CACHE_ROOT=/workspace/.cache/vllm` and the supplied XDG, Torch, and Triton cache paths. SGLang needs both `SGLANG_CACHE_DIR` and `SGLANG_JIT_CACHE_DIR` in the writable workspace.
- **Low-bit selection:** normal BF16 serving keeps `HYPERLOOM_GFX1151_LOWBIT_BRIDGE="0"`. Enable a supported format through the serving helper, not a global environment change.
- **Shared memory:** choose `--kv-cache-memory-bytes` for the actual context and concurrency. The quickstart's small budget is not a general recommendation.
- **Native profiling:** retain the vLLM image/Compose library and Kineto settings. Custom benchmark environment values can override them; [build notes](docs/BUILD.md#vllm-native-kineto-runtime-wiring) contain the exact required values.

</details>

## Documentation and reproducibility

- [User guide](docs/USAGE.md): serving, authentication, quantization, optimization, and configuration.
- [Build guide](docs/BUILD.md): rebuild using public release inputs or fetch pinned component sources.
- [Test results and limitations](docs/QUALIFICATION.md): verification details and links to the original evidence records.
- [Component manifest](manifests/components.json): exact source commits, image references, and digests.
- [Release downloads](https://github.com/HawgAuto/HaloLoom/releases/tag/v0.1.2): Hyperloom wheel, build-input archive, and checksums. Normal users install the container images rather than assembling these assets manually.
- [Security policy](SECURITY.md) and [upstream credits](NOTICE.md).

Native Codex packaging, authentication, build verification and resume controls:
[native agent runtime](docs/native-agent-runtime.md).
