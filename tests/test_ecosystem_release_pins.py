"""The immutable verifier pins follow the checked-in release manifest."""
import importlib.util
import hashlib
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("name,key,framework", [("Hyperloom","hyperloom",False),("GEAK","geak",False),("IntelliKit","intellikit",False),("vllm","vllm",True),("sglang","sglang",True)])
def test_ecosystem_verifier_matches_release_component(name, key, framework):
    spec = importlib.util.spec_from_file_location("release_ecosystem_verifier", ROOT / "scripts/verify_ecosystem.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    components = json.loads((ROOT / "manifests/components.json").read_text())["components"]
    refs = module.EXPECTED_FRAMEWORK_REFS if framework else module.EXPECTED_REFS
    assert refs[name] == components[key]["commit"]


def test_current_runtime_registry_has_its_own_digest_without_relabelling_history():
    component = json.loads((ROOT / "manifests/components.json").read_text())["components"]["hyperloom"]
    current = ROOT / component["runtime_registry_snapshot"]
    assert hashlib.sha256(current.read_bytes()).hexdigest() == component["runtime_registry_sha256"]
    historical = json.loads((ROOT / "qualification/readiness/FUNCTIONAL-TARGET-MATRIX.json").read_text())
    assert component["public_registry_sha256"] == historical["registry_sha256"]
    assert "historical" in component["public_registry_scope"]
