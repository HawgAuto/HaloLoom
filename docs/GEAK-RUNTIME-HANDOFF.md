# Bundled AMD SMI and GEAK Setup handoff

## Source-bound vLLM signal and profiler lifecycle

Package `scripts/apply_source_current_overlay.py` byte-for-byte as the native
archive's `apply-and-verify.py`. It synchronizes both the validated Qwen loader
and `vllm/entrypoints/launcher.py`, updates and verifies their existing wheel
RECORD entries, and retains the immutable native-library/source-identity checks.
If the base carries an earlier pre-applied vLLM overlay, the archive must declare
its exact predecessor commit and tree. Reconciliation requires full working-tree
equality and ancestry before advancing; unknown local edits remain a hard error.
A source checkout containing a repair is not proof that the imported installed
package contains it. Verify both paths, metadata hashes, and real HTTP shutdown
in the final image without development-source mounts.

The paired vLLM patch leaves embedded-server signal handling to the existing
vLLM event-loop coordinator. This avoids restoring a native profiler handler
represented by Python as None; it does not guess defaults or monkey-patch the
signal module. GEAK's opt-in `SERVER_STOP_SCOPE=parent` lets that coordinator
drain its workers before the existing identity-bound deadline cleanup. Profile
load clients retain their independent tree cleanup. For external capture only,
pair parent-first stop with a positive native `--shutdown-timeout` and a longer
driver grace. Keep ordinary unprofiled benchmark policy unchanged.

Qualification proceeds through no-device HTTP SIGINT/SIGTERM tests, a tiny real
spawned-worker capture, then real-model export and the original engagement/A-B
gates. Native Torch/Kineto geometry is a separate path: CPU-tested upstream
decoder changes are not an installed Torch fix or permission to fill missing
grid values from configuration. Publish matching source/archive/image pins only
after the appropriate installed-image and workflow gates pass.

## Bundled AMD SMI registration

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
