# Third-party notices

HaloLoom is a distribution and integration project. It does not rename or claim authorship of its upstream components.

| Component | Upstream | License |
|---|---|---|
| Hyperloom | https://github.com/AMD-AGI/Hyperloom | MIT (repository LICENSE) |
| KernelForge (bundled by Hyperloom) | https://github.com/AMD-AGI/Hyperloom | MIT (repository LICENSE) |
| Magpie | https://github.com/AMD-AGI/Magpie | MIT |
| TraceLens | https://github.com/AMD-AGI/TraceLens | MIT |
| GEAK | https://github.com/AMD-AGI/GEAK | Apache-2.0 |
| IntelliKit | https://github.com/AMDResearch/intellikit | MIT |
| InferenceX | https://github.com/SemiAnalysisAI/InferenceX | Apache-2.0 |
| vLLM | https://github.com/vllm-project/vllm | Apache-2.0 |
| SGLang | https://github.com/sgl-project/sglang | Apache-2.0 |
| AMD Quark | https://github.com/amd/Quark | MIT |
| AITER | https://github.com/ROCm/aiter | MIT |


Pinned revisions and artifact checksums are authoritative in `manifests/components.json` and the release checksum manifest. Each release artifact retains its own embedded license metadata where supplied by upstream.

The optional Strix Halo low-bit kernels and vLLM/SGLang consumer adapters are published and versioned separately at https://github.com/HawgAuto/Strix-Halo-Lowbit-Kernel-Pack. The v0.1 SGLang image preserves and pins its golden closure. The v0.1 vLLM image preserves the compact v16 dependency closure and installs the separately source-bound full vLLM/low-bit wheels by exact SHA-256. The deferred core flavor excludes the pack.

AITER is included only in the optional tools image. The default SGLang route keeps AITER attention disabled because the tested BF16 GQA2 geometry did not qualify.

Claude Code, Codex CLI and Hermes Agent are not redistributed by HaloLoom. A user-selected existing host installation is mounted at runtime as an external plug-in under that tool's own license and account terms.
