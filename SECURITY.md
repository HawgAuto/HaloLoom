# Security policy

## Reporting

Please use GitHub's private vulnerability-reporting flow for the HawgAuto/HaloLoom repository. Do not include credentials, private model URLs, access tokens, local filesystem paths, or proprietary model data in a public issue.

## Execution boundary

HaloLoom's agent control plane runs inside a non-root framework Docker container and must not receive the host Docker socket. The selected host agent installation is mounted read-only; its existing configuration home is mounted separately. No agent executable or credential is copied into a release image.

Writable Hermes transports fail closed unless both an explicit opt-in and a concrete container marker are present. Codex uses its native workspace-write sandbox. These controls reduce risk but do not make untrusted model output safe to execute without review.

GPU launch wrappers hold the shared `/run/lock/hermes-vllm-gfx1151.lock`, check `/dev/kfd` ownership, and never kill unrelated processes automatically.

## Secrets

Keep API keys and OAuth state outside this repository. Pass credentials through the documented runtime environment/profile mounts. Release manifests, image labels, command lines and logs must contain no credential values.
