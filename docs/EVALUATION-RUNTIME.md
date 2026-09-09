# Native evaluator runtime packaging

The source-current vLLM, SGLang and Quark images install the evaluator at build time, before task namespace qualification. The native optimizer must not need runtime pip writes into `/opt/venv`.

`docker/evaluation/requirements.lock` pins the evaluator additions and wheel hashes. Release-input assembly must include those exact wheels and an identical lock at `dist/source-current/evaluation-wheels/`; the enclosing source-current manifest binds every file. The supported Dockerfile uses offline, no-dependency, hash-required installation. Ship the matching archive whenever updating this recipe; an older archive without this directory is incompatible and must fail rather than fetch from the network.

The wheel set excludes Torch, Triton, ROCm, Transformers, datasets, NumPy and serving frameworks. The image's existing runtime provides them. Qualify imports and the actual native evaluation command as the serving UID, not root, and verify the inherited package versions/native identities remain unchanged. A Python CLI help pass is not task execution or a model accuracy claim.

MIOpen's cache and user database default to `/workspace/.cache/miopen` and `/workspace/.cache/miopen_db` in both Compose and direct source-current images. The workspace must be writable by the serving UID. These environment defaults apply before framework imports; they replace campaign-only cache exports, not the quantization policy.

The current Qwen functional campaign intentionally leaves full GSM8K off. Keep product evaluation available without silently enabling a full dataset run or treating bounded generation as a quality pass.
