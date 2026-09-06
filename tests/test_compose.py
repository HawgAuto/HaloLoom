from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def _compose():
    return yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))


def test_no_service_mounts_docker_socket_and_all_run_as_host_uid() -> None:
    # The standalone control container was removed; agent dispatch runs inside
    # the framework services. No service may reach the host Docker socket, and
    # every service that bind-mounts host agent roots runs as the host UID.
    services = _compose()["services"]
    assert "control" not in services
    for name, service in services.items():
        mounts = "\n".join(service.get("volumes", []))
        assert "/var/run/docker.sock" not in mounts, name
        if name != "aiter-tools":
            assert service["user"] == "${HOST_UID}:${HOST_GID}", name


def test_gpu_services_have_only_explicit_amd_devices_and_groups() -> None:
    services = _compose()["services"]
    for name in ("vllm", "sglang", "quark", "aiter-tools"):
        service = services[name]
        assert service["devices"] == ["/dev/kfd:/dev/kfd", "/dev/dri:/dev/dri"]
        assert service["group_add"] == ["${VIDEO_GID}", "${RENDER_GID}"]
        assert service["ipc"] == "host"


def test_release_compose_has_versioned_images_and_no_source_mount() -> None:
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "Strix-Halo-Lowbit-Kernel-Pack" not in text
    for service in _compose()["services"].values():
        assert service["image"].startswith("ghcr.io/hawgauto/")
        assert service["image"].endswith(":${HALOLOOM_VERSION}")


def test_primary_servers_use_full_golden_compact_images() -> None:
    services = _compose()["services"]
    assert services["vllm"]["image"] == (
        "ghcr.io/hawgauto/haloloom-vllm-full-gfx1151:${HALOLOOM_VERSION}"
    )
    assert services["sglang"]["image"] == (
        "ghcr.io/hawgauto/haloloom-sglang-full-gfx1151:${HALOLOOM_VERSION}"
    )
    assert services["aiter-tools"]["image"] == (
        "ghcr.io/hawgauto/haloloom-aiter-tools-full-gfx1151:${HALOLOOM_VERSION}"
    )
    assert services["vllm"]["entrypoint"] == [
        "/opt/venv/bin/python3",
        "-m",
        "vllm.entrypoints.openai.api_server",
    ]
    assert services["sglang"]["entrypoint"] == [
        "/opt/venv/bin/python3",
        "-m",
        "sglang.launch_server",
    ]


def test_readme_invokes_existing_python_launcher() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/serve.sh" not in text
    assert "python3 scripts/serve.py vllm" in text
    assert "python3 scripts/serve.py sglang" in text


def test_every_gpu_service_pins_one_coherent_rocm_runtime() -> None:
    services = _compose()["services"]
    for name in ("vllm", "sglang", "quark", "aiter-tools"):
        environment = services[name]["environment"]
        assert environment["ROCM_PATH"] == "/opt/rocm/core-10.0"
        assert environment["ROCM_HOME"] == "/opt/rocm/core-10.0"
        assert environment["HIP_PATH"] == "/opt/rocm/core-10.0"
        loader = "/opt/rocm/core-10.0/lib:/opt/rocm/core-10.0/lib/llvm/lib:/opt/venv/lib"
        if name == "vllm":
            loader = (
                "/opt/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/host-math/lib:"
                + loader
            )
        assert environment["LD_LIBRARY_PATH"] == loader
        assert "HSA_OVERRIDE_GFX_VERSION" not in environment
