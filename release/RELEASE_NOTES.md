# HaloLoom v0.1.0

Turnkey ROCm 10 / AMD Radeon 8060S (`gfx1151`) distribution of the faithful Hyperloom port.

## Included

- reviewed Hyperloom wheel `hyperloom_inference_optimizer-1.0.0-py3-none-any.whl` (`sha256:9cc9884911db814c8d72d7e1219fe580f94f98849674f3b468f16caf3a8e09de`)
- full vLLM and SGLang serving workbench images
- faithful Quark agent image
- optional AITER tools/JIT image
- installed pinned Magpie, IntelliKit Metrix, TraceLens, GEAK, InferenceX and built-in KernelForge
- Compose, preflight, source-sync, serving and quantization launchers
- automatic read-only plug-in for an existing host Claude Code, Codex or Hermes CLI; no agent CLI is bundled

Exact public image references and registry digests are in `manifests/components.json`.

## Low-bit package

The six-route HIP module and framework adapters are independently owned and released at:

https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack/releases/tag/v0.1.0

All six routes pass direct physical qualification. W4A8 additionally passes final-image vLLM and SGLang request/dispatch qualification. No performance win is claimed.

## Boundaries

- Native `gfx1151` is required; do not set `HSA_OVERRIDE_GFX_VERSION`.
- SGLang uses Triton attention with CUDA graphs disabled.
- AITER core, gemm-common and RMSNorm canaries pass; AITER greedy sampling and AITER attention are unavailable.
- The prior Quark INT8 PTQ candidate was quality-rejected; no quantization quality win is claimed.
- Clean low-bit-free framework wheels are provenance-bound but are not v0.1 images because they have not passed separate physical serving.
- Nothing is promoted into an existing production service automatically.
