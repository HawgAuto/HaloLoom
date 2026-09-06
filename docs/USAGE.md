# HaloLoom user guide

Start with the [README quickstart](../README.md#quickstart). This guide covers choosing an agent, serving models, running Quark, and using Hyperloom's optimizer. Commands are run from the HaloLoom repository root unless stated otherwise.

## Install and choose an agent

The host needs Docker/Compose, a working AMD GPU driver, Git, Python 3, and an existing agent CLI. HaloLoom supplies the inference libraries and compiler tools inside its images; it does not install a host Python package environment.

```bash
./scripts/install.sh --agent codex
```

Replace `codex` with `claude` or `hermes` to select another installed CLI. The default `--agent auto` looks for Codex, then Hermes, then Claude. Codex and Hermes have recorded optimizer-readiness tests; Claude integration is available but does not have the same recorded end-to-end coverage. The [test documentation](QUALIFICATION.md) distinguishes these results.

Useful installer options:

- `--include-aiter`: also pull the optional AITER tools image.
- `--sync-sources`: fetch pinned component checkouts for development. Ordinary use does not require these additional host checkouts.
- `--include-build-sources`: include framework build sources when syncing.
- `--no-pull`: configure paths without downloading images.

The installer writes local configuration to `.env`. Keep it out of version control and do not replace it with an untrusted file. Your selected CLI installation is mounted read-only at its existing path; its configuration and login data use separate mounts. Codex's host auth mount is read-only; Claude and Hermes auth-home mounts are writable. See [security](../SECURITY.md) before using sensitive credentials.

Check the installed workbench and CLI:

```bash
./scripts/haloloom vllm verify
./scripts/haloloom vllm agent-check
./scripts/haloloom sglang --help
```

## Authentication

There are two distinct uses of an LLM in the optimizer:

1. **Orchestration:** Hyperloom plans and reviews the optimization work.
2. **Candidate authoring:** KernelForge and GEAK use the selected agent CLI to propose code.

Selecting an agent plug-in does not automatically supply every credential needed by orchestration. In particular, a Hermes-only login is not an orchestration login.

| Account | Setup for the optimizer |
|---|---|
| ChatGPT / Codex subscription | Run `codex login` on the host and select `--agent codex`. With a valid Codex auth file and no `OPENAI_API_KEY` or `OPENAI_BASE_URL` set, the workbench uses the subscription login for all OpenAI-side optimizer roles. |
| Claude Pro / Max subscription | Run `claude setup-token` and set `CLAUDE_CODE_OAUTH_TOKEN` in the shell used to launch HaloLoom. |
| OpenAI API | Set `OPENAI_API_KEY`; set `OPENAI_BASE_URL` only when using a compatible gateway. |
| Anthropic API | Set `ANTHROPIC_API_KEY` in the launching shell. |

Keep credentials in your shell or existing CLI login, not in commands saved to the repository, Compose YAML, or model prompts. The wrapper forwards allowlisted variable **names**, not their values in process arguments. Values still exist in the running container environment and are visible to Docker administrators.

### Codex subscription details

HaloLoom's `native_oauth` support follows Hyperloom's existing subscription-based client design. It does not replace the optimizer's tests, reviews, or acceptance checks. API-key users retain the normal API path.

The workbench copies the read-only host `auth.json` into a mode-0600 location under the container's temporary `/tmp` directory. It sets `INFERENCE_OPTIMIZER_CODEX_AUTH_MODE=native_oauth` and `INFERENCE_OPTIMIZER_CODEX_HOME` for the optimizer. The temporary copy disappears with the container; the host login is not modified. Explicit native-OAuth configuration combined with an API key or base URL is rejected rather than silently switching credentials.

Docker is the external sandbox for this Codex path. Keep the supplied `HYPERLOOM_CODEX_EXTERNAL_SANDBOX=1`, `HYPERLOOM_CODEX_SANDBOX_MODE=bypass`, and `GEAK_CODEX_EXTERNAL_SANDBOX=1` settings together with the workbench's writable-root restrictions. A container reduces exposure; it does not make arbitrary agent-generated code safe. Review commands and use credentials appropriate to the task.

## Model paths and downloaded files

By default, `workspace/` in the checkout is mounted at `/workspace` inside the containers. Place a local model under `workspace/models/<name>` and refer to it inside a prompt or server command as `/workspace/models/<name>`. The actual host workspace and Hugging Face cache paths are recorded in your generated `.env`.

Hugging Face model IDs can be passed directly to the serving helper. The first run downloads weights into the configured cache. Pin a revision for reproducibility. For local cached snapshots, ensure symlink targets are also accessible inside the container.

Run one GPU workload at a time. The launch helpers hold `/run/lock/hermes-vllm-gfx1151.lock` and check GPU ownership. Stop your own current workload before launching another; HaloLoom does not terminate unrelated services.

## Serve with vLLM

The [quickstart](../README.md#2-start-a-small-text-model) provides a complete Qwen3.5-0.8B example. The helper syntax is:

```text
python3 scripts/serve.py vllm MODEL --model-revision COMMIT \
  --max-model-len CONTEXT_LENGTH -- FRAMEWORK_ARGUMENTS
```

Arguments before `--` configure the HaloLoom helper; arguments after it go to vLLM. The server stays in the foreground; use Ctrl+C to stop it.

### Shared-memory sizing

Strix Halo shares memory between CPU and GPU. vLLM's percentage-based memory profiler can fail its free-memory snapshot assertion when host memory is released during profiling. An explicit `--kv-cache-memory-bytes` avoids that automatic sizing step.

The published small-model API test used a 512-token context, one sequence, a 268435456-byte KV cache, BF16, eager loading/execution, Triton attention, and `--language-model-only`. The README adapts those model settings to a Hugging Face download. The recorded test itself used a cached revision with private loopback/resource-limit overrides; it does not prove every host, model, multimodal input, or memory setting.

For a larger model or longer context, size weights, KV cache, and runtime overhead together. Do not reuse the small example's budget as a universal setting. Keep native `gfx1151` detection and leave `HSA_OVERRIDE_GFX_VERSION` unset.

## Serve with SGLang

This example uses the same small Qwen3.5 model with model-specific Mamba settings:

```bash
python3 scripts/serve.py sglang Qwen/Qwen3.5-0.8B \
  --model-revision 2fc06364715b967f1860aea9cf38778875588b17 \
  --max-model-len 512 -- \
  --mem-fraction-static 0.12 --mamba-ssm-dtype float32 \
  --max-mamba-cache-size 32 --mamba-radix-cache-strategy extra_buffer
```

The helper supplies Triton attention, disables CUDA graphs and radix caching, and disables mmap and multithreaded weight loading. Do not override its attention/graph flags. The published SGLang image passed model-request testing with the shipping Compose environment; this example is not a new performance benchmark.

Both `SGLANG_CACHE_DIR=/workspace/.cache/sglang` and `SGLANG_JIT_CACHE_DIR=/workspace/.cache/sglang/jit` are needed. Keep them in a writable workspace; setting only an XDG or Triton cache path does not replace them.

Use the same `/v1/chat/completions` API as the README example. SGLang and vLLM both publish port 8000, so do not run both examples simultaneously.

## Network and model security

The default Compose mapping is `8000:8000`, which publishes the server on host interfaces, not just loopback. The example API has no authentication enabled. Use a trusted network, firewall, or authenticated proxy as appropriate.

For local-only use, change the port mapping of the service you intend to run in your **local** `compose.yaml` from `8000:8000` to `127.0.0.1:8000:8000` before launching. Do not change the container's internal port. This is an optional local configuration change, not a setting applied by the quickstart.

The serving helper enables `--trust-remote-code`. Load only model repositories and revisions you trust. The standard Compose services also mount configured agent/auth homes; they are not credential-free sandboxes. For sensitive use, review those mounts and the full [security policy](../SECURITY.md).

## Quantize with Quark

Use the Quark image through Hyperloom's `quantization-agent` workflow. Replace the agent-model placeholder with a model supported by your selected CLI:

```bash
python3 scripts/quantize.py \
  --workspace qwen-w8a8 \
  --model-id <agent-model-id> \
  --prompt 'Quantize the model at /workspace/models/Qwen3-0.6B with W8A8 and preserve lm_head.'
```

- `--workspace` is a new or existing task-directory name under the mounted workspace.
- `--model-id` selects the **agent's model**, not the model being quantized.
- `--prompt` identifies the target model and quantization requirements. Place the model at the specified path first.
- The provider must match the CLI selected by the installer; rerun `install.sh --agent ...` to change it.

Keep secrets out of prompts and model IDs: both may appear in process listings and logs. Inspect the workflow's exported artifacts and validator results. A successful export is not proof of acceptable model quality, and an unavailable evaluation is not a passing score. Validate the output for your own workload before using it.

## Optimize a model

Initialize and inspect the optimizer's workspace once before the first run:

```bash
./scripts/haloloom vllm readiness initialize
./scripts/haloloom vllm readiness status
./scripts/haloloom vllm optimize --help
```

Then select a model and framework:

```bash
./scripts/haloloom vllm optimize --model <hf-model-id> --framework vllm \
  --gpu-type radeon8060s

# Alternative: use the SGLang workbench.
./scripts/haloloom sglang optimize --model <hf-model-id> --framework sglang \
  --gpu-type radeon8060s
```

The host CLI authors candidates while profiling, compilation, and testing run beside the selected framework inside the container. HIP (`hipcc`), Torch extension tooling, and Triton JIT are included. No host Docker socket is mounted.

For vLLM, pass an explicit KV-cache budget through Hyperloom's existing server-argument option if automatic shared-memory sizing fails:

```text
./scripts/haloloom vllm optimize --model MODEL --framework vllm \
  --gpu-type radeon8060s \
  --server-args "--kv-cache-memory-bytes BYTES --enforce-eager"
```

Choose `BYTES` for your actual workload. If setting optimizer timing limits, use a tick interval of at least one second and allow enough time for loading and benchmarking. A zero interval can exhaust the limit while asynchronous work is still starting.

### Apply results deliberately

Hyperloom's final `reports/final.json` records accepted configuration details, including `extra_server_args` and `extra_envs`. Review the report and its tests, then apply the accepted settings to a serving configuration yourself. Framework arguments go after `--` in `scripts/serve.py`; supported environment settings belong in your local runtime configuration. Preserve required library and cache paths.

HaloLoom does not automatically promote a candidate, update a production model registry, or replace an existing service. A working optimizer does not promise that every model or candidate will improve.

## Optional low-bit kernels

The [Strix Halo Low-bit Kernel Pack](https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack) is independently released and pinned by HaloLoom. Its presence in the full images does not enable it for ordinary BF16 serving.

For an explicitly selected route, put the exact model revision before `--` and the framework's quantization option after it:

```bash
python3 scripts/serve.py vllm Qwen/Qwen3.5-0.8B \
  --model-revision 2fc06364715b967f1860aea9cf38778875588b17 \
  --max-model-len 2048 -- --quantization gfx1151-w4a8
```

Use this as a route-selection example, not a blanket recommendation for memory sizing or performance. The helper enables the bridge only for the explicitly selected `gfx1151-*` format; there is no `--lowbit` flag. For normal BF16 operation, leave `HYPERLOOM_GFX1151_LOWBIT_BRIDGE="0"` unchanged.

The six-format module and framework integrations have different evidence scopes. W4A8's original cross-framework request/dispatch checks belong to the recorded v0.1.0 image lineage; the v0.1.1 runtime checks do not automatically re-test those routes. Consult [test results](QUALIFICATION.md) and the pack's own documentation for exact coverage. No general speedup is promised.

## Build and verification references

- [Build guide](BUILD.md): public rebuild, source pins, and exact native-profiler environment settings.
- [Test results](QUALIFICATION.md): runtime, optimizer, route, and installation evidence with their limits.
- [Component manifest](../manifests/components.json): exact versions and image digests.
- [Security](../SECURITY.md): credential mounts, writable workspaces, and agent-execution risks.
