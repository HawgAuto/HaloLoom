from __future__ import annotations

import re
from pathlib import Path


RECIPE_PATH = Path(__file__).parents[1] / "docker" / "source-current" / "Dockerfile"
KINETO_CLIENT = "/opt/venv/lib/python3.14/site-packages/torch/lib/libtorch_cpu.so"
KINETO_LIBRARY_PATH = (
    "/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/host-math/lib:"
    "/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib"
)
PATCH_SHA256 = "a2280f784472ec202010541b86b20de19837b8582bf5bbc151718aaefabb0b86"


def stages() -> dict[str, str]:
    recipe = RECIPE_PATH.read_text(encoding="utf-8")
    matches = list(re.finditer(r"(?m)^FROM\s+\S+\s+AS\s+(\S+)\s*$", recipe))
    return {
        match.group(1): recipe[match.start() : matches[index + 1].start() if index + 1 < len(matches) else None]
        for index, match in enumerate(matches)
    }


def test_recipe_exposes_exact_public_release_targets() -> None:
    assert tuple(stages()) == ("source-current", "vllm", "sglang", "quark")


def test_vllm_target_alone_adds_kineto_runtime_environment() -> None:
    recipe_stages = stages()
    assert f"ENV ROCP_TOOL_LIBRARIES={KINETO_CLIENT}" in recipe_stages["vllm"]
    assert f"LD_LIBRARY_PATH={KINETO_LIBRARY_PATH}" in recipe_stages["vllm"]
    for name in ("source-current", "sglang", "quark"):
        assert "ROCP_TOOL_LIBRARIES=" not in recipe_stages[name]
        assert "LD_LIBRARY_PATH=" not in recipe_stages[name]


def test_sglang_target_applies_exact_reviewed_patch_as_root_then_verifies_as_user() -> None:
    stage = stages()["sglang"]
    copy = "COPY --chown=1000:1000 dist/source-current/tracelens-sglang-0519/ /opt/haloloom/tracelens-sglang-0519/"
    apply = "RUN /opt/venv/bin/python3 /opt/haloloom/tracelens-sglang-0519/apply-reviewed-patch.py"
    user = "USER 1000:1000"
    verify = "RUN /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py"
    assert "FROM source-current AS sglang" in stage
    assert "USER root" in stage
    assert copy in stage
    assert apply in stage
    assert f'haloloom.tracelens_sglang_patch_sha256="{PATCH_SHA256}"' in stage
    assert stage.index("USER root") < stage.index(copy) < stage.index(apply) < stage.index(user) < stage.index(verify)


def test_quark_target_is_an_unmodified_source_current_alias() -> None:
    assert stages()["quark"].strip() == "FROM source-current AS quark"
