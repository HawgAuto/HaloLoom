"""Writable MIOpen defaults belong to the product, not campaign exports."""
from pathlib import Path
import shlex

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "MIOPEN_CUSTOM_CACHE_DIR": "/workspace/.cache/miopen",
    "MIOPEN_USER_DB_PATH": "/workspace/.cache/miopen_db",
}


def docker_environment(relative):
    text = (ROOT / relative).read_text().replace("\\\n", " ")
    values = {}
    for line in text.splitlines():
        if line.startswith("ENV "):
            for token in shlex.split(line[4:]):
                key, value = token.split("=", 1)
                values[key] = value
    return values


@pytest.mark.parametrize("service", ["vllm", "sglang", "quark", "aiter-tools"])
def test_compose_sets_both_miopen_paths_on_writable_workspace(service):
    config = yaml.safe_load((ROOT / "compose.yaml").read_text())
    environment = config["services"][service]["environment"]
    for name, value in EXPECTED.items():
        assert environment.get(name) == value


@pytest.mark.parametrize("recipe", [
    "docker/source-current/Dockerfile",
    "docker/ecosystem/Dockerfile",
    "docker/quark/Dockerfile",
])
def test_direct_images_do_not_depend_on_compose_for_miopen(recipe):
    environment = docker_environment(recipe)
    for name, value in EXPECTED.items():
        assert environment.get(name) == value
