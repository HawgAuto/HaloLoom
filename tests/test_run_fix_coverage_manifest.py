"""Integrity of the source-only reconciliation ledger, not image qualification."""
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def documents():
    pins = json.loads((ROOT / "manifests/source-fixes-20260926.json").read_text())
    ledger = json.loads((ROOT / pins["coverage_manifest"]).read_text())
    return pins, ledger


def test_every_historical_ledger_id_has_one_disposition():
    _, ledger = documents()
    ids = [row["id"] for row in ledger["rows"]]
    assert ids == [f"HLFP-{n:03d}" for n in range(1, 51)]
    assert ledger["row_count"] == len(ids) == len(set(ids))
    assert dict(Counter(row["historical_classification"] for row in ledger["rows"])) == ledger["classification_counts"]
    assert dict(Counter(row["delivery_status"] for row in ledger["rows"])) == ledger["delivery_counts"]


def test_source_delivery_and_exclusions_are_explicit():
    _, ledger = documents()
    for row in ledger["rows"]:
        if row["historical_classification"] == "hypothesis_open":
            assert row["delivery_status"] == "not_adopted_open_hypothesis"
        elif row["historical_classification"] == "reverted_unadopted":
            assert row["delivery_status"] == "excluded_rejected_candidate"
        else:
            assert row["references"]
        for ref in row["references"]:
            assert ref["repository"].startswith("https://github.com/")
            assert re.fullmatch(r"[0-9a-f]{40}", ref["ref"])
    extras = ledger["supplementary_fixes"]
    assert len({row["id"] for row in extras}) == len(extras) == 3


def test_source_completion_does_not_grant_image_or_runtime_authority():
    pins, ledger = documents()
    assert pins["source_reconciliation_complete"] is True
    assert ledger["complete"] is True
    assert ledger["source_publication_only"] is True
    assert pins["unresolved_publication_items"] == {}
    assert pins["image_release_published_by_this_task"] is False
    assert pins["production_activation"] is False
    assert pins["stable_release_manifests_unchanged"] is True
    for component in pins["components"].values():
        assert component["installed_runtime_updated_by_this_task"] is False
        assert component["anonymous_source_readback"] is True
