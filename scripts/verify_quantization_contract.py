#!/usr/bin/env python3
"""Parse HaloLoom's public quantizer argv in the installed runtime.

This is a no-device, no-provider-call build gate, not a quantization smoke.
"""
from __future__ import annotations

import json


def main() -> int:
    from hyperloom.agents.quantization.cli import _parse_args

    providers = ("claude", "codex", "hermes")
    for provider in providers:
        args = _parse_args([
            "--provider", provider,
            "--prompt", "Quantize /workspace/model with W8A8",
            "--workspace", "/workspace/cli-contract",
            "--interactive", "off",
            "--model-id", "operator-selected-agent-model",
        ])
        if args.provider != provider or args.model_id != "operator-selected-agent-model":
            raise RuntimeError(f"quantization CLI contract mismatch for {provider}")
    print(json.dumps({"status": "PASS", "providers": providers, "scope": "parser_only"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
