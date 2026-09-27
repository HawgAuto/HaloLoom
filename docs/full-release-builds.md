# Complete source-bound runtime builds

The v0.1.4 build path integrates the accepted Quark/serving and MTP repairs,
TraceLens/profiler changes, and GEAK/Hyperloom/Arbor and native-agent routing
changes as one versioned source packet. The installer version changes only
when the corresponding public image manifests have been verified.

## Availability and loader-path scope

This is a **build interface**, not an announcement that v0.1.4 images are
published. The stable installer and `manifests/components.json` retain their
last released image selection until registry readback succeeds. A source-fix
branch or source commit does not change the image installed by that manifest.
The examples below consume the manifest actually present in the checkout;
they do not implicitly select an unpublished v0.1.4 packet.

`docker/full-release/compose.runtime.yaml` preserves the full-runtime
image-specific loader closures. It is intentionally **opt-in**, not a root
`compose.override.yaml`: applying the Python 3.14 wheel-SDK paths automatically
to older stable images would mix incompatible closures. After selecting and
verifying matching full-runtime images, inspect the merged configuration:

```bash
docker compose -f compose.yaml -f docker/full-release/compose.runtime.yaml config
```

This overlay changes loader paths only, not image selection. Keep the wheel SDK
before copied SDK libraries to avoid loading two COMGR implementations; vLLM /
Quark and SGLang use different paths. Explicit private overrides follow this
file. Do not use the overlay with a different interpreter or ROCm layout.

## Rebuild the release

Use the checked-out release's actual manifest; do not substitute a local image
ID for a registry manifest digest.

```bash
./scripts/build_images.sh
```

Schema 4 is dispatched by the original `scripts/build_release_inputs.py` front
door to `scripts/build_full_release_inputs.py`. Older schema consumers remain
available with their existing semantics and tests. To verify/download the
packet without pulling or building runtime images:

```bash
./scripts/build_images.sh --prepare-only --output-dir "$PWD/dist/packet-check"
```

For offline packet verification, add `--archive /absolute/path/to/full-release-inputs.tar.gz`.
The output directory must not already exist. Use `--image vllm`, `--image quark`
or `--image sglang` to select a build. No accelerator devices are attached during
assembly. Source verification may also be run in a device-enabled container;
it does not start inference or grant production authority.

## Identity and runtime boundaries

- The packet binds all five changed component commits, trees, wheel versions
  and wheel hashes. Source and installed Python/native package files are
  independently compared. Git's mutable index cache is not a source identity.
- The vLLM composite retains the donor's exact native extension bytes and records
  its native donor hash separately from the integrated Python source commit.
- Quark retains separate Python 3.12 quantizer and Python 3.14 serving environments.
  Its bundled serving runtime must receive the same accepted serving/MTP repair
  union as the vLLM image, not just a newer source checkout next to an old install.
- Native agent executable/source, the repaired ROCm profiler SDK, and unchanged
  retained toolkit references are separately bound. Existing agent-audit evidence
  is retained; packaging checks are not a new agent audit.
- The build installs the current repository's Quark plug-in entrypoint explicitly,
  rather than silently inheriting an older wrapper from a runtime base.
- Final compaction preserves user, working directory, shell, entrypoint and
  environment. It does not grant hardware, performance or production authority.

The archive hash is checked before parsing. The full packet allows bounded
in-tree source symlinks, rejects escaping paths, duplicate members and unsupported
file types, and applies explicit member and compressed/unpacked size limits.
These format rules do not relax legacy packet extractors.

## Claims

Source tests, wheel identity, installed-file identity, native compiler checks,
real model requests and public-registry readback are separate evidence states.
A passing source verifier is not a model-quality or performance result. Historical
MTP draft/proposer/cache evidence is not full-target MTP acceptance. Release
publication does not restart paused optimization work or activate production
services. Model checkpoints, quantized exports and private campaign reports are
not part of this software release.
