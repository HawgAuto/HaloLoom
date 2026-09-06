# Security policy

## Reporting

Please use GitHub's private vulnerability-reporting flow for the HawgAuto/HaloLoom repository. Do not include credentials, private model URLs, access tokens, local filesystem paths, or proprietary model data in a public issue.

## Execution boundary

HaloLoom's agent control plane runs inside a non-root framework Docker container and must not receive the host Docker socket. The selected host agent installation is mounted read-only; its existing configuration home is mounted separately. Codex auth is read-only, while the existing Claude and Hermes auth-home mounts are writable because those workflows may update their state. No agent executable or credential is copied into a release image.

For Codex `native_oauth`, the host `~/.codex` mount is read-only. The workbench copies only `auth.json` into a mode-0600 directory under the container's ephemeral `/tmp`, points the existing Codex role there, and removes it with the `--rm` container. No credential is copied into the image, repository, persistent workspace, manifest, label, argv, or log. Any API key/base URL set alongside `native_oauth` is rejected instead of silently shadowing the subscription login.

Writable Hermes transports fail closed unless both an explicit opt-in and a concrete container marker are present. For Codex `native_oauth`, Docker is the external sandbox and the workbench sets `HYPERLOOM_CODEX_EXTERNAL_SANDBOX=1` plus `HYPERLOOM_CODEX_SANDBOX_MODE=bypass` because the image intentionally does not ship bubblewrap; each role's existing Hyperloom/KernelForge writable-root allowlist still applies. These controls reduce risk but do not make untrusted model output safe to execute without review.

GPU launch wrappers hold the shared `/run/lock/hermes-vllm-gfx1151.lock`, check `/dev/kfd` ownership, and never kill unrelated processes automatically.

## Secrets

Keep API keys and OAuth state outside this repository. Pass credentials through the documented runtime environment/profile mounts. Release manifests, image labels, command lines and logs must contain no credential values.

`scripts/haloloom` forwards an allowlisted credential only when it is already set in the invoking shell, using Docker Compose's name-only `-e NAME` form. This keeps the value out of `.env`, Compose YAML, the repository, and process argv, but the value is present in the container environment and can be read through container inspection by users with Docker/administrator access. Child tools may expose environment values in diagnostics, so use least-privilege, short-lived credentials. Do not run `docker compose config` with credentials embedded in YAML; HaloLoom does not require that pattern.

`/workspace/.env`, when present, is sourced by a shell and must be treated as trusted executable code, not an inert data file. Keep untrusted workspaces and downloaded `.env` files out of this path. The quantization prompt and `--model-id` may appear in process listings or logs; never place tokens, private URLs, proprietary text, or other secrets in them.

Writable Claude/Hermes auth homes expose their contents to code running in the workbench and can be modified by that code. Review agent-generated commands and isolate credentials appropriate to the task; containerization and writable-root allowlists reduce risk but are not a trust boundary against malicious model output.
