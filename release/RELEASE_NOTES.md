# HaloLoom v0.1.1

**A container-based toolkit for running and improving LLM inference on AMD Strix Halo.**

HaloLoom brings Hyperloom, vLLM, SGLang, AMD Quark, and GPU profiling tools together in a pinned ROCm 10 environment for the Radeon 8060S (`gfx1151`). It is designed for users who want to serve models, quantize them, or explore agent-assisted optimization without assembling the underlying Python and GPU toolchains on the host.

[Quickstart](https://github.com/HawgAuto/HaloLoom#quickstart) · [User guide](https://github.com/HawgAuto/HaloLoom/blob/main/docs/USAGE.md) · [Build guide](https://github.com/HawgAuto/HaloLoom/blob/main/docs/BUILD.md) · [Test results](https://github.com/HawgAuto/HaloLoom/blob/main/docs/QUALIFICATION.md)

## What's included

- **vLLM and SGLang images** for OpenAI-compatible model serving and Hyperloom optimization.
- **AMD Quark** for agent-assisted model quantization.
- **KernelForge and GEAK** for generating, compiling, and testing kernel candidates.
- **Magpie, InferenceX, TraceLens, and IntelliKit Metrix** for benchmarks, accuracy checks, and GPU profiling.
- **Optional AITER tools** for selected kernel-development tasks.
- Install, verification, serving, quantization, source-fetch, and rebuild helpers.
- Integration with an existing **Claude Code, Codex, or Hermes CLI**. Agent executables are not bundled in the images.

## What's new in v0.1.1

- Native Radeon 8060S detection and the corresponding vLLM/SGLang benchmark runners in the optimizer.
- Codex/ChatGPT subscription login support across the OpenAI-side optimizer roles, alongside the existing API-key and Claude subscription paths.
- Working vLLM native GPU profiling with the required library settings included in the image and Compose configuration.
- Updated SGLang 0.5.19 development sources and writable runtime/JIT cache settings for non-root operation.
- A public, checksum-verified rebuild workflow using pinned base images and a downloadable build-input archive.

Exact component commits and image references are listed in the [release manifest](https://github.com/HawgAuto/HaloLoom/blob/v0.1.1/manifests/components.json).

## Get started

The host needs Linux with a working AMD GPU driver, Docker with Compose v2, Git, Python 3, access to the `video`/`render` groups, and an installed supported agent CLI. Model capacity depends on available RAM and the requested context and concurrency.

```bash
git clone https://github.com/HawgAuto/HaloLoom.git
cd HaloLoom
unset HSA_OVERRIDE_GFX_VERSION
./scripts/install.sh
./scripts/haloloom vllm verify
```

The installer pulls the vLLM, SGLang, and Quark images. Add `--include-aiter` for the optional tools image or `--agent codex` to choose a CLI explicitly. It does not install Docker, the kernel driver, an agent CLI, or host Python packages.

Follow the [quickstart](https://github.com/HawgAuto/HaloLoom#quickstart) to start a small model and send an API request. The full optimizer also needs supported orchestration credentials; a Hermes CLI alone does not provide them. See [authentication](https://github.com/HawgAuto/HaloLoom/blob/main/docs/USAGE.md#authentication).

## Downloads and rebuilding

Most users should install the published container images rather than assemble the release files manually. The attached assets are:

- `hyperloom_inference_optimizer-1.0.0-py3-none-any.whl` — the pinned Hyperloom package used by the images; not a standalone installation of the full stack.
- `haloloom-v0.1.1-build-inputs.tar.gz` — the source and overlay inputs used by the public rebuild workflow.
- `SHA256SUMS` — checksums for the wheel and archive.

To rebuild, use `./scripts/build_images.sh` as described in the [build guide](https://github.com/HawgAuto/HaloLoom/blob/main/docs/BUILD.md). Framework builds use the pinned public bases; AITER is reused at its recorded digest.

## Tested behavior and current limits

Release checks covered an anonymous clone and image installation, 123 passing tests, a public rebuild, and a real API response from the released vLLM image. Native vLLM profiling and SGLang/Quark model requests were also exercised. Detailed configurations, results, and original evidence records are in [Test results and limitations](https://github.com/HawgAuto/HaloLoom/blob/main/docs/QUALIFICATION.md).

Before use:

- Keep native `gfx1151` detection; do not set `HSA_OVERRIDE_GFX_VERSION`.
- Use a fixed vLLM KV-cache budget if shared-memory changes trip automatic sizing. The published small-model API check was text-only, not broad multimodal coverage.
- Keep SGLang's supplied Triton attention configuration with CUDA graphs disabled. Graph discovery, capture/replay, and EAGLE operation are outside current test coverage.
- AITER attention and sampling are unavailable. Optional [low-bit kernels](https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack) have separate, model/framework-specific coverage.
- The default server port is published on host interfaces without API authentication. Restrict access, trust your model sources, and read the [security policy](https://github.com/HawgAuto/HaloLoom/blob/main/SECURITY.md).

Quantization and optimization results must be evaluated for your workload; no general quality or speed improvement is promised. HaloLoom does not automatically change existing inference services or apply optimizer results.
