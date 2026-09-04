# Support Boundaries

## Supported for functional optimization

Hyperloom can discover, exactly select, bind, propose source for, materialize, and deterministically evaluate every target in registry v3.

### vLLM

- RDNA HybridW4A16 HIP decode
- RDNA HybridW4A16 Triton prefill
- generic Triton W4A16 fallback
- archive W4A4 performance quantizer
- archive W4A4 V4Q M128 quantizer
- archive W4A4 M1 pair2 DOT8
- archive W4A4 M128 v3 WMMA
- W4A4 DOT baseline
- W4A4 padded WMMA baseline
- W4A4 DOT M-tile 4
- W4A4 DOT M-tile 8
- W4A4 WMMA 16×64
- W4A4 WMMA 32×64
- W4A4 WMMA 32×32
- W8A8 dynamic-token INT8 quantizer
- W8A8 Triton scaled matmul
- Python W4A4 dispatcher policy as control-only

### SGLang

- FP8 E4M3 FNUZ
- MXFP4 E2M1/E8M0
- W8A8
- W4A8
- W4A4
- W4A16

Each SGLang-native method has a real Qwen3.5-0.8B request-owned route receipt on ROCm10/gfx1151.

## Framework isolation

vLLM-private kernels are not silently exposed through SGLang. SGLang-native kernels are not silently exposed through vLLM. Registry rows explicitly mark unavailable cross-framework pairs. New sharing requires a separately registered adapter and proof.

## Optimizer engines and providers

- GEAK has a real gfx1151 GPU candidate lifecycle.
- KernelForge and CandidateControl are source-current and regression-tested.
- Native Codex OAuth and Hermes/OpenAI-Codex are qualified source-only provider arms on `gpt-5.6-sol` with no fallback.
- Claude wiring remains available but was not selected for the qualified readiness epoch.
- Deterministic compile/correctness/decision authority remains outside agents.

## What readiness does not claim

- no new candidate performance win;
- no candidate adoption;
- no universal best kernel or model profile;
- no SGLang/vLLM cross-framework ABI equivalence beyond explicit rows;
- no NPU/XDNA operation;
- no production router, registry, service, model, or fleet activation;
- no automatic promotion authority.

Future optimization campaigns may now use the ready system without reopening platform/registry/GEAK/SGLang/control-plane functionality unless source or runtime identities change.
