"""The local Codex/AMD overlay retains an exact, verifiable GEAK checkout."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "docker/codex-amd-overlay/Dockerfile"
GEAK_REF = "cd1af9459f00d3d785978852c2b3399e90d72853"


def test_overlay_clones_geak_bundle_and_checks_out_exact_ref() -> None:
    recipe = RECIPE.read_text()
    assert "COPY GEAK.bundle /opt/haloloom/source-current/GEAK.bundle" in recipe
    assert "git clone --no-local /opt/haloloom/source-current/GEAK.bundle" in recipe
    assert f"git -C /opt/haloloom/components/GEAK checkout --detach {GEAK_REF}" in recipe
    assert f'test "$(git -C /opt/haloloom/components/GEAK rev-parse HEAD)" = "{GEAK_REF}"' in recipe
    assert "rm -rf /opt/haloloom/components/GEAK" in recipe
    assert "COPY GEAK/ /opt/haloloom/components/GEAK/" not in recipe


def test_overlay_runs_inherited_ecosystem_verifier_with_candidate_geak_ref() -> None:
    recipe = RECIPE.read_text()
    assert "COPY verify_ecosystem.py /opt/haloloom/verify_ecosystem.py" in recipe
    assert "RUN /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py" in recipe
    verifier = (ROOT / "docker/codex-amd-overlay/verify_ecosystem.py").read_text()
    assert f'"GEAK": "{GEAK_REF}"' in verifier