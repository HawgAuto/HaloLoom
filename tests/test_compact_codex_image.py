"""CPU-only fail-closed tests for the Codex OCI layer compactor."""

import importlib.util
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "compact_codex_image.py"
SPEC = importlib.util.spec_from_file_location("haloloom_compact_codex_image", MODULE)
assert SPEC is not None and SPEC.loader is not None
compact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compact)


def source():
    return {"Id": "sha256:" + "a" * 64, "Config": {
        "Env": ["PATH=/opt/venv/bin:/usr/bin", "WORD=quoted with spaces"],
        "Labels": {"haloloom.promotion_authority": "false", "origin": "HaloLoom"},
        "User": "1000:1000", "WorkingDir": "/workspace", "Entrypoint": ["/bin/sh", "-c"],
        "Cmd": ["true"], "Shell": ["/bin/bash", "-o", "pipefail", "-c"],
    }}


def test_generator_restricts_source_restores_metadata_and_compacts():
    old = source()
    recipe = compact.dockerfile("candidate:v1", old, True, {"haloloom.geak_ref": "cd1af945"})
    assert "FROM candidate:v1 AS resolved" in recipe
    assert "FROM scratch\nCOPY --from=resolved / /" in recipe
    assert "codex-amd-source-rust-v0.153.4.tar.gz" in recipe
    assert "ENV WORD=\"quoted with spaces\"" in recipe
    assert "SHELL [\"/bin/bash\", \"-o\", \"pipefail\", \"-c\"]" in recipe
    assert "/opt/haloloom/verify_ecosystem.py" in recipe
    assert 'LABEL haloloom.oci_compacted="true"' in recipe


@pytest.mark.parametrize("bad", ["candidate;touch /unsafe", "candidate\nFROM evil", ""])
def test_generator_rejects_unsafe_image_reference(bad):
    with pytest.raises(ValueError, match="Unsafe image reference"):
        compact.dockerfile(bad, source(), False, {})


def test_generator_refuses_promotion_and_volume_loss():
    old = source()
    with pytest.raises(ValueError, match="cannot grant promotion"):
        compact.dockerfile("candidate:v1", old, False, {"haloloom.promotion_authority": "true"})
    old["Config"]["Volumes"] = {"/data": {}}
    with pytest.raises(ValueError, match="Unsupported"):
        compact.dockerfile("candidate:v1", old, False, {})


def test_verify_detects_layer_and_config_drift():
    old = source()
    new = {"RootFS": {"Layers": ["sha256:only-layer"]},
           "Config": {**old["Config"], "Labels": {**old["Config"]["Labels"],
                        "haloloom.oci_compacted": "true", "haloloom.oci_compacted_from": old["Id"]}}}
    compact.verify(old, new, {})
    new["RootFS"]["Layers"].append("sha256:old-bytes")
    with pytest.raises(RuntimeError, match="exactly one"):
        compact.verify(old, new, {})
    new["RootFS"]["Layers"].pop()
    new["Config"]["Env"] = []
    with pytest.raises(RuntimeError, match="config drift"):
        compact.verify(old, new, {})
