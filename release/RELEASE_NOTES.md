# HaloLoom v0.1.1

Turnkey ROCm 10 / AMD Radeon 8060S (`gfx1151`) distribution of the faithful Hyperloom port.

This is the immutable turnkey successor to the initial `v0.1.0` publication. It adds the missing friend-facing `inference_optimizer optimize` board/runner closure: Hyperloom now accepts and auto-detects `radeon8060s` (`gfx1151`, 40 CUs), and Magpie maps `gfx1151` to its existing `vllm_radeon8060s.sh` / `sglang_radeon8060s.sh` runners. Every OpenAI-side LLM role — Orchestrator, critic review, robustness RCA, framework specialist, proposal scorer and framework audit — also gains Codex `native_oauth`, mirroring upstream's own Claude-subscription transport (`claude_oneshot`) and KernelForge's already-shipped Codex mode, so ChatGPT-subscription users run the full role set from their host `codex login` with no API key, proxy, or mocks. It also makes the Python 3.14 Ray override explicit at runtime, bounds/retries public source fetches, and forwards upstream orchestration credentials by variable name only.

## Included

- reviewed Hyperloom commit `b91cab3433002fa8381108dd5ea7cb3633b6955e`, tree `67a82a90bf85e54104da833565627354351ebc85`, and wheel `hyperloom_inference_optimizer-1.0.0-py3-none-any.whl` (`sha256:a0229171738133afbdffc91502006e9e872787d5350e7d438c3103064b058d23`)
- full vLLM and SGLang serving workbench images
- faithful Quark agent image
- optional AITER tools/JIT image
- installed pinned Magpie, IntelliKit Metrix, TraceLens, GEAK, InferenceX and built-in KernelForge
- Compose, preflight, source-sync, serving and quantization launchers
- automatic read-only plug-in for an existing host Claude Code, Codex or Hermes CLI; no agent CLI is bundled
- Codex subscription auth is copied from the read-only host mount into container-ephemeral `/tmp` mode 0600; the host login is never modified and the copy disappears with `docker compose run --rm`

Exact public image references and registry digests are in `manifests/components.json`.

Release assets are exactly `SHA256SUMS`, the current Hyperloom wheel, and `haloloom-v0.1.1-build-inputs.tar.gz` (54,043,592 bytes; SHA-256 `1829b58ae16459660e36e091f379131da7983f8d044a7f5fb6a48202d56a6ae5`). The supported fresh-clone rebuild is `./scripts/build_images.sh`, which uses one safe source-current recipe with targets `vllm`, `sglang`, and `quark`; AITER is digest-pinned and tagged without overlay.

Final source-current image IDs and anonymous OCI readbacks are in `manifests/components.json` and `qualification/receipts/release-closeout-v0.1.1.json`. All three final runtimes completed their physical gate with clean containment and unchanged production. The final vLLM image completed 16/16 requests at capture delay/max 128/128 with 128,912 GPU kernels and 193,713 HIP runtime events, using the baked native-profiler defaults. SGLang and Quark each passed the frozen five-request substring canary; this is not new exact-format or quality qualification. The release code suite passes 123 tests. Existing `*-final-v0.1.1.json` files remain historical lineage. The runtime receipt deliberately does not claim the later source/tag publication or anonymous installation checks.

## Low-bit package

The six-route HIP module and framework adapters are independently owned and released at:

https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack/releases/tag/v0.1.0

- All six routes pass direct physical qualification. W4A8 additionally has vLLM and SGLang request/dispatch qualification on the v0.1.0 image lineage; v0.1.1 separately proves BF16 serving and the bounded optimizer gate. No low-bit performance win is claimed.

## Boundaries

- Native `gfx1151` is required; do not set `HSA_OVERRIDE_GFX_VERSION`.
- SGLang is pinned at `0.5.19.dev0` commit `90c62e027831111934a33b9bcc4e533ff61d8526`; it uses default Triton attention with CUDA graphs disabled. The reviewed TraceLens 0.5.19 patch is strict/idempotent CPU payload only; graph-shape discovery, graph capture/replay and EAGLE runtime are not qualified.
- AITER core, gemm-common and RMSNorm canaries pass; AITER greedy sampling and AITER attention are unavailable.
- The prior Quark INT8 PTQ candidate was quality-rejected: bundled-source evaluation scored 4/16 versus 3/16 for quantized output, a 25% relative gap above the 3% limit. No quality or performance win is claimed.
- Clean low-bit-free framework wheels are provenance-bound but are not v0.1 images because they have not passed separate physical serving.
- Nothing is promoted into an existing production service automatically.
- Codex `native_oauth` adds a transport behind upstream's existing client seam; no role's prompts, contracts, gates or default (API-key) behaviour changes. Nothing is replaced with a mock.
- Optimizer attempt3 remains an actual `CLOSE`; it was not rerun. Evaluation/knowledge-base disabling and skipped GEAK native-budget work describe that attempt, not universal feature readiness.
- Historical original `ProfileExecutor` evidence is 16/16 requests, capture delay/max 128/128, 128,912 kernel events, 193,711 HIP runtime events, raw-trace SHA-256 `8614dc57f75a7ce0280fd3167c8862914cc7767c500d019c809d002e797d19e6`. The separate 997-kernel/1,169-HIP-event tiny-worker run is not the original profile.
