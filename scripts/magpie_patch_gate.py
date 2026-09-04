"""HaloLoom build-time gate for the Hyperloom Magpie/InferenceX script patcher.

Mirrors the exit policy of the qualified Hyperloom ``install.sh`` (the
authoritative consumer of ``magpie_scripts_patch_status``) instead of the
over-strict ``assert status.ok`` that rejected the pinned public Magpie:

* GENUINE atomic failure (``atomic_genuine_failure``) -> exit 4 (fatal).
  The Hyperloom #C1 script-tearing race would be unmitigated.
* Live ``run_eval --concurrent-requests`` flag surviving (``eval_flag_ok``
  False) -> exit 5 (fatal). Every RUN_EVAL=true baseline would abort.
* ``remote_trust_ok`` False -> exit 0 with a WARNING. This is the benign
  upstream-native case: the pinned Magpie already passes ``--trust-remote-code``
  on its SGLang client paths natively, so the legacy Hyperloom trust splice has
  no legacy block to match. ``install.sh`` treats this as ``warn``, not ``die``.
* ``atomic_ok`` False for a benign reason (missing/upstream) -> exit 0 with a
  WARNING (``install.sh`` fail-soft behaviour).

Usage: python3 magpie_patch_gate.py <MAGPIE_ROOT> <INFERENCEX_ROOT>
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: magpie_patch_gate.py <MAGPIE_ROOT> <INFERENCEX_ROOT>", file=sys.stderr)
        return 64
    magpie_root, inferencex_root = argv[1], argv[2]

    from hyperloom.orchestrator.actions.executors._magpie_patcher import (
        magpie_scripts_patch_status,
    )

    status = magpie_scripts_patch_status(magpie_root, inferencex_root)
    print(
        "HALOLOOM_MAGPIE_PATCH_STATUS "
        f"atomic_reason={status.atomic_reason} atomic_ok={status.atomic_ok} "
        f"remote_trust_ok={status.remote_trust_ok} eval_flag_ok={status.eval_flag_ok}"
    )
    if status.atomic_genuine_failure:
        print(
            "HALOLOOM_MAGPIE_PATCH_GATE FATAL: Magpie atomic-write patch GENUINELY "
            "failed (script-tearing race unmitigated).",
            file=sys.stderr,
        )
        return 4
    if not status.eval_flag_ok:
        print(
            "HALOLOOM_MAGPIE_PATCH_GATE FATAL: live 'run_eval --concurrent-requests' "
            "survives; RUN_EVAL=true baselines would abort.",
            file=sys.stderr,
        )
        return 5
    if not status.remote_trust_ok:
        print(
            "HALOLOOM_MAGPIE_PATCH_GATE WARNING: legacy SGLang trust splice not "
            "applicable (pinned Magpie passes --trust-remote-code natively on its "
            "SGLang client paths); continuing, matching Hyperloom install.sh policy.",
            file=sys.stderr,
        )
    if not status.atomic_ok:
        print(
            f"HALOLOOM_MAGPIE_PATCH_GATE WARNING: atomic patch no-op "
            f"(reason={status.atomic_reason}); benign.",
            file=sys.stderr,
        )
    print("HALOLOOM_MAGPIE_PATCH_GATE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
