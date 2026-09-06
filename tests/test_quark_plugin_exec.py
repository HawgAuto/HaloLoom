"""Exercise actual Quark entrypoint setup with a renamed host CLI."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_quark_entrypoint_exposes_the_selected_vendor_cli_name(tmp_path):
    vendor = tmp_path / 'vendor package' / 'renamed-cli'
    vendor.parent.mkdir()
    vendor.write_text('#!/usr/bin/env bash\nprintf "CLI_PROBE %s\\n" "$*"\n')
    vendor.chmod(0o755)
    source = (ROOT / 'docker/quark/plugin-entrypoint').read_text()
    # Run unchanged initialization, stopping immediately before GPU locking
    # and the real quantization-agent. No provider, device, or credentials.
    preamble, separator, _ = source.partition('if [[ "${HALOLOOM_PARENT_GPU_LOCK:-0}" == 1 ]]; then')
    assert separator
    env = dict(os.environ, HALOLOOM_AGENT_PROFILE='claude',
               HALOLOOM_CLAUDE_BIN_HOST=str(vendor), PATH='/usr/bin:/bin', TMPDIR=str(tmp_path))
    child = subprocess.run(['bash', '-c', preamble + '\nclaude --version\n',
                            'entrypoint-probe', '--workflow-init'],
                           capture_output=True, text=True, env=env)
    assert child.returncode == 0, child.stderr
    assert child.stdout == 'CLI_PROBE --version\n'
