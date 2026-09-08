# Bundled AMD SMI and GEAK Setup handoff

The source-current image assembly runs `scripts/install_bundled_amdsmi.py` from
the hash-bound overlay archive under the image's `/opt/venv/bin/python3`.
Include that tracked helper as `install_bundled_amdsmi.py` in the overlay archive;
no new Docker build-context allowlist is required. Its source identity belongs
to the paired HaloLoom commit in the candidate/release manifest.

A modular ROCm SDK carries AMD SMI at
`purelib/_rocm_sdk_core/share/amd_smi/amdsmi`. Images historically exposed that
path only through PYTHONPATH. GEAK's closed operational environment intentionally
excludes PYTHONPATH, so a normal `vllm` command in an agent shell could fail ROCm
platform discovery despite a working parent Magpie server.

The helper validates the bundled package's path and rejects symlinked or foreign
registration inputs before writing one relative, non-executable `.pth` entry.
It records source-file hashes and the registration hash in
`/opt/haloloom/bundled-amdsmi.json`. It does not install a different AMD SMI,
import the package, initialize devices, replace a platform class, or relax the
agent environment allowlist. Images without a modular SDK are explicitly marked
not applicable; an incomplete modular SDK fails assembly.

Verify the installed image with no development-source mounts:

```bash
/opt/venv/bin/python3 /opt/haloloom/source-current/install_bundled_amdsmi.py \
  --verify-only --report /opt/haloloom/bundled-amdsmi.json
env -u PYTHONPATH /opt/venv/bin/python3 -I -c 'import amdsmi; print(amdsmi.__file__)'
```

Those commands prove packaging/import provenance, not GPU operation. Under the
exclusive GPU lease, also exercise GEAK's exact scrubbed shell environment,
actual vLLM platform/parser, then a real native Setup and later kernel lifecycle.
The separate GEAK adapter must keep recipe/journal control metadata outside the
selected evaluation workspace. Preserve the original Director collision rule,
exact-directory validation, old legacy journals and failed attempts.
