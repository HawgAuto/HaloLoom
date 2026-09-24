# Complete source-bound runtime builds

The v0.1.4 build path integrates the accepted Quark/serving and MTP repairs,
TraceLens/profiler changes, and GEAK/Hyperloom/Arbor and native-agent routing
changes as one versioned source packet. The installer version changes only
when the corresponding public image manifests have been verified.

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

## Default Compose runtime configuration

Normal `docker compose` commands, including the installer and serving helpers,
automatically merge `compose.override.yaml` with `compose.yaml`. The override
selects each full image's verified loader path; it leaves device access, user,
entrypoint, profiling registration and other settings unchanged. The base file
and its historical regression contracts are retained byte-for-byte.

If you explicitly select Compose files, include the runtime override too:

```bash
docker compose -f compose.yaml -f compose.override.yaml config
```

Add any private overrides **after** those two files. Using the base file alone
with the new runtimes can select a second COMGR library and abort during native
imports. The vLLM/Quark and SGLang loader paths are intentionally different.

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
