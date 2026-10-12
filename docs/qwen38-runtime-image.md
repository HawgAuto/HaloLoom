# Qwen3.8 runtime integration image

This opt-in successor combines the accepted [run-fix reconciliation](run-fix-reconciliation.md)
with the current [HawgAuto/vLLM runtime](https://github.com/HawgAuto/vllm/tree/322c106f3409df1eeb29d2c14434b389b36c2b43/haloloom/qwen38).
The method and toolkit are **HaloLoom**. This does not replace the stable installer
images or promote the experimental native multi-request QSA candidate.

## Delivery status

- Source: runtime published at `322c106f3409df1eeb29d2c14434b389b36c2b43`.
- Image assembly, installed payload integrity and no-device compiler tests: passed.
- Final-image real-model gate: running; ordinary and singleton MTP3 use separate processes.
- Registry publication and immutable pull reference: pending that gate.
- Intended tag: `ghcr.io/hawgauto/haloloom-vllm-full-gfx1151:v0.1.5-qwen38`.
- No new model-quality or throughput claim is made by these release checks.

## Included changes

- Accepted profiler lifecycle, scalar MTP metadata, and protected-embedding fixes.
- PLE active-request/capacity row handling and graph-safe multi-row workspace.
- Native singleton QSA retained; concurrent requests use the request-aware Triton path.
- Reconciled optimizer, GEAK, TraceLens, Quark, native CLI and profiler SDK inputs.
- InferenceX's accepted portable launcher patch, applied over its known partially
  repaired predecessor without changing server binds.
- SDK CLI and code-mode-host entrypoints resolve to the same qualified native bundle.
- Source verification uses a disposable Git index, preserving the authenticated
  packet while still rejecting dirty source.
- Explicit Git ignore exceptions and a manifest-to-index regression prevent omission
  of HIP sources, native release binaries, and the HIP module loader.

The source packet retains complete installed component packages, native source,
reinstallable wheels, and exact ref/tree/hash bindings. Large unchanged TraceLens
fixture data is omitted by sparse checkout. The image retains the separate Quark
Python environment and updates its Transformers/tokenizers compatibility pair.

## Rebuild the exact packet

Use `docker/full-release/Dockerfile.qwen38`. The packet is hash-bound and contains
no model weights or credentials. Once the image is published, its offline packet
can be extracted from `/opt/haloloom/source-current` using a stopped container;
no GPU, host Python installation or provider login is needed to extract it.

```bash
docker buildx build --load --network=none \
  --build-context release_packet=/absolute/path/to/source-current \
  --build-arg PACKET_MANIFEST_SHA256=74a43ac800c0b9718074c9ff91b1a320145062cb4ba51f80145bb0a2b098c87f \
  -f docker/full-release/Dockerfile.qwen38 \
  -t haloloom-qwen38:local docker/full-release
```

This is a **layered combined-workbench image**, not a one-layer compaction. Its
published parent is pinned by digest. No protected predecessor images were pruned.

## Serving interface

The image preserves the workbench entrypoint and adds `qwen38`. Bind exactly one
complete variant at `/model` read-only and a writable cache directory at `/workspace`.
Expose the AMD `/dev/kfd` and its render node; do not assume the render-node number
is identical on every system. See the runtime README for full Docker examples.

- INT8-core ordinary: `qwen38 --variant int8 --mtp 0 --max-num-seqs 4`.
- BF16-core ordinary: `qwen38 --variant bf16 --mtp 0 --max-num-seqs 4`.
- MTP3, either variant: use `--mtp 3 --max-num-seqs 1`.
- Static model/index check: add `--cpu-check`; no GPU needed for this check.

MTP remains deliberately single-sequence guarded. The accepted concurrency sweep
covered ordinary submitted levels 1/2/4/8/16/32; 32 submitted requests did not mean
32 continuously overlapping decodes. These historical measurements are separate
from the final-image delivery gate. Multimodal quality and independent model-quality
qualification are not established by text-token smoke tests.
