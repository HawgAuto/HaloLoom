#!/usr/bin/env python3
"""Compatibility entrypoint for the full-release CPU integrity check."""
import os
from pathlib import Path
import sys

variant = os.environ.get('HALOLOOM_RELEASE_VARIANT')
if variant not in {'vllm', 'sglang', 'quark'}:
    raise SystemExit('Missing or invalid full-release variant')
script = Path('/opt/haloloom/source-current/apply_and_verify.py')
os.execv(sys.executable, [sys.executable, str(script), '--verify-only', '--variant', variant])
