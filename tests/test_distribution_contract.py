from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _bytes(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def test_public_base_uses_pinned_public_rocm_images() -> None:
    dockerfile = _text("docker/rocm10-gfx1151-base/Dockerfile")
    assert "docker.io/rocm/dev-ubuntu-26.04:10.0.0-full@sha256:" in dockerfile
    assert (
        "docker.io/rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0@sha256:"
        in dockerfile
    )
    assert "hyperloom-rocm10-qualifier" not in dockerfile
    assert "HSA_OVERRIDE_GFX_VERSION" not in dockerfile


def test_unqualified_core_runtime_recipes_are_not_published() -> None:
    for directory in ("docker/vllm-core", "docker/sglang-core"):
        assert not (ROOT / directory / "Dockerfile").exists()
        assert not (ROOT / directory / "requirements.lock").exists()


def test_quark_image_uses_golden_runtime_and_original_skill_entrypoint() -> None:
    dockerfile = _text("docker/quark/Dockerfile")
    assert (
        "ARG GOLDEN_IMAGE=haloloom-quark-golden-base-gfx1151:v0.1.0-rc1" in dockerfile
    )
    assert "pip install" not in "\n".join(
        line for line in dockerfile.splitlines() if "amd_quark" in line
    )
    assert "/opt/haloloom-agent/bin/pip install" in dockerfile
    assert "hyperloom_inference_optimizer-1.0.0-py3-none-any.whl[runtime]" in dockerfile
    assert "cmp /opt/haloloom/golden-identity-before.json" in dockerfile
    assert "COPY docker/quark/plugin-entrypoint /opt/haloloom/quark-entrypoint" in dockerfile
    assert 'ENTRYPOINT ["/opt/haloloom/quark-entrypoint"]' in dockerfile
    entrypoint = _text("docker/quark/plugin-entrypoint")
    assert "/opt/haloloom-agent/bin/quantization-agent" in entrypoint
    assert "HALOLOOM_AGENT_PROFILE" in entrypoint
    assert "flock -x /run/lock/hermes-vllm-gfx1151.lock" in entrypoint
    assert "HALOLOOM_PARENT_GPU_LOCK" in entrypoint
    assert "HSA_OVERRIDE_GFX_VERSION" not in dockerfile
    assert "hermes-agent" not in dockerfile
    assert "@openai/codex" not in dockerfile
    assert "@anthropic-ai/claude-code" not in dockerfile
    assert "HALOLOOM_AGENT_BIN_DIR=/opt/haloloom/agent-bin" in dockerfile
    assert "ROCM_PATH=/opt/rocm/core-10.0" in dockerfile
    assert "HIP_PATH=/opt/rocm/core-10.0" in dockerfile
    before_identity = dockerfile.split("golden-identity-before.json", 1)[1].split(
        "RUN apt-get", 1
    )[0]
    assert "--package hyperloom-inference_optimizer" not in before_identity


def test_final_full_images_layer_only_bound_wheels_without_dependency_resolution() -> (
    None
):
    vllm = _text("docker/full-vllm-release/Dockerfile")
    sglang = _text("docker/full-sglang-release/Dockerfile")
    assert "FROM haloloom-vllm-full-gfx1151:v0.1.0-rc1" in vllm
    assert "FROM haloloom-sglang-full-gfx1151:v0.1.0-rc1" in sglang
    for dockerfile in (vllm, sglang):
        assert "pip install --no-index --no-deps" in dockerfile
        assert "requirements.lock" not in dockerfile
        assert "LOWBIT_WHEEL_SHA256" in dockerfile
        assert (
            'haloloom.lowbit_overlay="strix-halo-lowbit-kernel-pack-0.1.0"'
            in dockerfile
        )
    assert "VLLM_WHEEL_SHA256" in vllm
    assert "0.27.0+haloloom.full.gfx1151.rocm10.rocm100" in vllm
    assert "ACTIVE_RUNTIME_SHA256" in vllm
    assert "hyperloom_rdna35_runtime.py /opt/hyperloom-runtime/" in vllm
    assert "7d082d7adb59c0afd51c63790410e03d40adf31b1dc03c0611ab62629055c1a3" in vllm


def test_aiter_tools_image_compacts_exact_golden_without_pip() -> None:
    dockerfile = _text("docker/aiter-tools/Dockerfile")
    assert (
        "ARG GOLDEN_IMAGE=hyperloom-sglang-v0515-rocm10:aiter-gfx1151-current-main-v3"
        in dockerfile
    )
    assert "pip install" not in dockerfile
    assert "runtime-identity-before.json" in dockerfile
    assert "runtime-identity-after.json" in dockerfile
    assert 'haloloom.aiter_attention_qualified="false"' in dockerfile
    assert "ROCM_PATH=/opt/rocm/core-10.0" in dockerfile
    assert "HIP_PATH=/opt/rocm/core-10.0" in dockerfile
    assert "import aiter" not in dockerfile
    assert "find_spec('aiter')" in dockerfile
    assert _text("compose.yaml").count('SGLANG_USE_AITER: "0"') >= 2


def test_released_images_do_not_bundle_external_agent_clis() -> None:
    assert not (ROOT / "docker/control/Dockerfile").exists()
    for relative in ("docker/ecosystem/Dockerfile", "docker/quark/Dockerfile"):
        dockerfile = _text(relative)
        assert "hermes-agent" not in dockerfile
        assert "@openai/codex" not in dockerfile
        assert "@anthropic-ai/claude-code" not in dockerfile
        assert "npm install" not in dockerfile


def test_framework_workbench_declares_hyperloom_user_data_path() -> None:
    dockerfile = _text("docker/ecosystem/Dockerfile")
    compose = _text("compose.yaml")
    assert "USER_DATA_PATH=/workspace" in dockerfile
    assert "USER_DATA_PATH: /workspace" in compose
    assert "  vllm:\n    <<: *gpu-common" in compose
    assert "  sglang:\n    <<: *gpu-common" in compose


def test_component_manifest_has_complete_source_provenance() -> None:
    data = json.loads(_text("manifests/components.json"))
    components = data["components"]
    expected = {
        "hyperloom",
        "magpie",
        "tracelens",
        "geak",
        "intellikit",
        "inferencex",
        "vllm",
        "sglang",
        "quark",
        "aiter",
        "lowbit_kernel_pack",
    }
    assert set(components) == expected
    assert components["vllm"]["lowbit_pack_bundled"] is False
    assert components["sglang"]["lowbit_pack_bundled"] is False
    assert components["lowbit_kernel_pack"]["bundled_in_full"] is True
    assert components["lowbit_kernel_pack"]["bundled_in_deferred_core"] is False
    assert (
        components["hyperloom"]["wheel_sha256"]
        == "a0229171738133afbdffc91502006e9e872787d5350e7d438c3103064b058d23"
    )
    for name in (
        "hyperloom",
        "magpie",
        "geak",
        "intellikit",
        "vllm",
        "sglang",
        "quark",
        "aiter",
    ):
        assert components[name]["repository"].startswith("https://github.com/")
        assert len(components[name]["commit"]) == 40


def test_release_inventory_is_only_four_images_and_three_assets() -> None:
    data = json.loads(_text("manifests/components.json"))
    assert set(data["images"]) == {
        "full_vllm",
        "full_sglang",
        "quark",
        "aiter_tools",
    }
    release = json.loads(_text("manifests/release-assets.json"))
    assert release["tag"] == "v0.1.1"
    assert [row["name"] for row in release["assets"]] == [
        "SHA256SUMS",
        "hyperloom_inference_optimizer-1.0.0-py3-none-any.whl",
        "haloloom-v0.1.1-build-inputs.tar.gz",
    ]
    for row in release["assets"]:
        source = ROOT / row["source"]
        if source.exists():
            assert source.stat().st_size == row["bytes"]
            assert hashlib.sha256(source.read_bytes()).hexdigest() == row["sha256"]
    sums = _text("release/SHA256SUMS").splitlines()
    assert sums == [
        (
            "a0229171738133afbdffc91502006e9e872787d5350e7d438c3103064b058d23  "
            "hyperloom_inference_optimizer-1.0.0-py3-none-any.whl"
        ),
        (
            "1829b58ae16459660e36e091f379131da7983f8d044a7f5fb6a48202d56a6ae5  "
            "haloloom-v0.1.1-build-inputs.tar.gz"
        ),
    ]


def test_intellikit_is_a_pinned_required_transitive_profiler() -> None:
    data = json.loads(_text("manifests/components.json"))
    intellikit = data["components"]["intellikit"]
    assert intellikit["commit"] == "2f61453a779980b00504ea3b772ff4a1a1c3f4ad"
    assert intellikit["role"] == "required_transitive_profiler"
    assert intellikit["required_packages"] == ["metrix"]
    assert "accordo" in intellikit["optional_source_packages"]
    assert intellikit["gfx1151_support"] == "metrix_native"
    assert intellikit["rocm10_support"] is True

    readme = _text("README.md")
    assert "IntelliKit" in readme
    assert "Metrix" in readme
    assert "reference-only" not in readme


def test_turnkey_ecosystem_layer_is_exactly_pinned() -> None:
    dockerfile = _text("docker/ecosystem/Dockerfile")
    exact_refs = {
        "HYPERLOOM_REF": "eaca6d848babfe0bf969e7bc442bcffcec829e85",
        "MAGPIE_REF": "25681df93ba21a1a6b0bdd4151884f42eead1063",
        "TRACELENS_REF": "a59a9c165bb64c7c416fd7cf79149803d552e43c",
        "GEAK_REF": "b4dea3fa33ef438d4233aae0ed2c2f425c4e419a",
        "INTELLIKIT_REF": "2f61453a779980b00504ea3b772ff4a1a1c3f4ad",
        "INFERENCEX_REF": "3d5581562f643f9bdeb8410cd924e2c70906c966",
        "VLLM_SOURCE_REF": "6ddd7a77a256e90f86c108eeed4ce46602cf9657",
        "SGLANG_SOURCE_REF": "cb9e016cb33b98bc804a57bc70b8272d8e8d134c",
    }
    for name, value in exact_refs.items():
        assert f"ARG {name}={value}" in dockerfile
    assert "GEAK_SKIP_BOOTSTRAP=1" in dockerfile
    assert "HSA_OVERRIDE_GFX_VERSION" not in dockerfile
    assert "metrix" in dockerfile
    assert "TraceLens_generate_perf_report_pytorch_inference" in dockerfile
    assert "kernelforge gemm-tune --help" in dockerfile
    assert "interface/run_e2e.py" in dockerfile
    assert "https://github.com/HawgAuto/vllm.git" in dockerfile
    assert "https://github.com/HawgAuto/sglang.git" in dockerfile
    assert "INFERENCE_OPTIMIZER_FRAMEWORK_SOURCE_ROOTS" in dockerfile
    assert "ray[default]==2.55.0" in dockerfile
    assert "click>=8.4.2,<9" in dockerfile
    assert "RAY_VERSION=2.55.0" in dockerfile
    assert "RAY_CLI_CLICK_MAX_VERSION=9.0.0" in dockerfile
    assert "PIP_CHECK_NO_NEW_CONFLICTS" in dockerfile
    # The low-bit pack and Hyperloom share the hyperloom namespace. Reinstalling
    # Hyperloom alone after the runtime layer can remove the pack's adapter
    # files. The ecosystem layer must verify and reinstall both distributions
    # together, then prove both adapter modules remain importable.
    assert "strix_halo_lowbit_kernel_pack-0.1.0-py3-none-any.whl" in dockerfile
    assert "e06d773292cb05c45fc61fffb251fcace49ef387c284c00208fb1827248ed8ad" in dockerfile
    assert "rdna35_lowbit_adapter" in dockerfile
    assert "rdna35_lowbit_hip" in dockerfile
    assert 'force-reinstall "$lowbit"' in dockerfile
    assert dockerfile.rindex('force-reinstall "$lowbit"') < dockerfile.index(
        'find_spec("hyperloom.inference_optimizer.rdna35_lowbit_adapter")'
    )
    tracelens_patch = _text("patches/tracelens/python314-xprof-2.20.2.patch")
    assert '-        "xprof==2.20.1"' in tracelens_patch
    assert '+        "xprof==2.20.2"' in tracelens_patch
    # xprof 2.20.2 only needs protobuf>=3.19.6; TraceLens's <7 bound is stale and
    # would force a downgrade of the qualified SGLang base's protobuf 7.36.0.
    assert '-        "protobuf>=6.31.1,<7.0.0"' in tracelens_patch
    assert '+        "protobuf>=6.31.1,<8.0.0"' in tracelens_patch
    # Each golden base keeps its own protobuf: it is constraint-pinned, never
    # explicitly re-pinned by the ecosystem layer.
    assert "for package in torch torchvision torchaudio triton grpcio protobuf; do" in dockerfile
    assert "'protobuf>=6.31.1,<7'" not in dockerfile
    assert "git -C /opt/haloloom/components/TraceLens apply" in dockerfile
    # Public-source fetches are bounded and retried from a fresh repo; a flaky
    # connection must not wedge a friend/maintainer build for 68 minutes.
    assert "for attempt in 1 2 3" in dockerfile
    assert "timeout 300 git -C" in dockerfile
    assert "http.lowSpeedTime=60" in dockerfile
    assert "rm -rf \"$root/$name\"" in dockerfile
    # Magpie patcher gate must mirror the qualified Hyperloom install.sh policy:
    # fail only on a genuine atomic failure or a live eval flag; an
    # upstream-native trust path (remote_trust_ok=False, benign) is a warning.
    assert "magpie_patch_gate.py" in dockerfile
    assert "assert s.ok" not in dockerfile
    gate = _text("scripts/magpie_patch_gate.py")
    assert "magpie_scripts_patch_status" in gate
    assert "atomic_genuine_failure" in gate
    assert "eval_flag_ok" in gate
    assert "return 4" in gate and "return 5" in gate
    # Component checkouts are chowned to 1000:1000 but compose runs as
    # ${HOST_UID}:${HOST_GID}; git must trust those exact image-owned roots for
    # any runtime UID or `verify`/readiness fail with "dubious ownership".
    assert "git config --system --add safe.directory /opt/haloloom/components/" in dockerfile
    assert "git config --system --add safe.directory /opt/haloloom/framework-source/" in dockerfile
    # The build-time verifier must run AFTER the chown so it exercises the
    # non-owner path (root != 1000) rather than passing trivially as owner.
    assert dockerfile.index("chown -R 1000:1000") < dockerfile.index(
        "verify_ecosystem.py >/opt/haloloom/ecosystem-verification.json"
    )
    entrypoint = _text("docker/ecosystem/workbench-entrypoint")
    assert "export INFERENCE_OPTIMIZER_FRAMEWORK_SOURCE_ROOTS=" in entrypoint
    assert "INFERENCE_OPTIMIZER_FRAMEWORK_SOURCE_ROOTS" in entrypoint.split(
        "for name in", 1
    )[1]


def test_quark_plugin_selects_the_existing_external_codex_mode() -> None:
    entrypoint = _text("docker/quark/plugin-entrypoint")
    assert "export HYPERLOOM_CODEX_EXTERNAL_SANDBOX=1" in entrypoint
    assert "export HYPERLOOM_CODEX_SANDBOX_MODE=bypass" in entrypoint
    assert 'export HYPERLOOM_CODEX_HOME="$CODEX_HOME"' in entrypoint


def test_built_images_parse_all_advertised_quark_providers() -> None:
    for dockerfile in ("docker/ecosystem/Dockerfile", "docker/quark/Dockerfile"):
        content = _text(dockerfile)
        assert "COPY scripts/verify_quantization_contract.py" in content
        assert "python3 /opt/haloloom/verify_quantization_contract.py" in content


def test_external_agent_clis_are_plugins_not_bundled() -> None:
    dockerfile = _text("docker/ecosystem/Dockerfile")
    for forbidden in (
        "NousResearch/hermes-agent",
        "@openai/codex",
        "@anthropic-ai/claude-code",
        "npm install",
    ):
        assert forbidden not in dockerfile
    assert 'haloloom.external_agent_clis_bundled="false"' in dockerfile
    entrypoint = _text("docker/ecosystem/workbench-entrypoint")
    assert "HALOLOOM_AGENT_BIN_DIR" in entrypoint
    assert "HALOLOOM_CLAUDE_BIN_HOST" in entrypoint
    assert "HALOLOOM_CODEX_BIN_HOST" in entrypoint
    assert "HALOLOOM_HERMES_BIN_HOST" in entrypoint
    assert "GEAK_AGENT_PROFILE" in entrypoint
    assert "FORGE_AGENT_CLI" in entrypoint
    assert "HYPERLOOM_HERMES_BIN" in entrypoint
    assert "agent-check" in entrypoint


def test_friend_facing_hyperloom_runs_inside_framework_container() -> None:
    launcher = _text("scripts/haloloom")
    installer = _text("scripts/install.sh")
    assert "docker compose run" in launcher
    assert "--entrypoint /opt/haloloom/workbench-entrypoint" in launcher
    assert '-e FRAMEWORK="$backend"' in launcher
    assert "vllm|sglang" in launcher
    assert "python3 -m venv" not in installer
    assert "pip install" not in installer
    assert "pull_services=(vllm sglang quark)" in installer
    assert 'docker compose pull "${pull_services[@]}"' in installer
    # Secret values stay in the invoking shell. The wrapper forwards only env
    # variable NAMES (`docker compose run -e NAME`), never values in argv/.env.
    for name in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL",
    ):
        assert name in launcher
    assert 'secret_env_args+=("-e" "$name")' in launcher


def test_runtime_caches_live_in_the_writable_workspace_not_bind_mount_parent() -> None:
    """Compose mounts only ``~/.cache/huggingface`` under the image home.

    Docker creates the parent ``/home/haloloom/.cache`` as root; a non-root vLLM
    worker therefore cannot create sibling ``.cache/vllm`` there. All mutable
    runtime/JIT caches must be rooted in the user-owned workspace instead.
    """
    compose = _text("compose.yaml")
    expected = {
        "XDG_CACHE_HOME": "/workspace/.cache",
        "VLLM_CACHE_ROOT": "/workspace/.cache/vllm",
        "VLLM_CONFIG_ROOT": "/workspace/.config/vllm",
        "TORCHINDUCTOR_CACHE_DIR": "/workspace/.cache/torchinductor",
        "TRITON_CACHE_DIR": "/workspace/.cache/triton",
    }
    for name, value in expected.items():
        assert f"{name}: {value}" in compose
    entrypoint = _text("docker/ecosystem/workbench-entrypoint")
    for name in expected:
        assert f'"${name}"' in entrypoint


def test_default_bf16_services_disable_the_optional_lowbit_bridge() -> None:
    """The archived low-bit request wrapper imports an optional adapter only
    when explicitly enabled. Normal BF16 vLLM/SGLang services must both override
    the image's low-bit-capable default to 0; ``serve.py --lowbit`` re-enables it
    together with an exact model revision.
    """
    compose = _text("compose.yaml")
    for service, next_service in (("vllm", "sglang"), ("sglang", "quark")):
        block = compose[compose.index(f"  {service}:") : compose.index(f"  {next_service}:")]
        assert 'HYPERLOOM_GFX1151_LOWBIT_BRIDGE: "0"' in block
    serve = _text("scripts/serve.py")
    assert '"HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1"' in serve
    assert "LOWBIT_MODEL_REVISION" in serve


def test_strix_halo_control_plane_footguns_are_documented() -> None:
    readme = _text("README.md")
    build = _text("docs/BUILD.md")
    for required in (
        "Strix Halo control-plane footguns",
        "--tick-interval-sec 1",
        "HYPERLOOM_CODEX_EXTERNAL_SANDBOX=1",
        "VLLM_CACHE_ROOT=/workspace/.cache/vllm",
        'HYPERLOOM_GFX1151_LOWBIT_BRIDGE="0"',
        "--kv-cache-memory-bytes",
    ):
        assert required in readme
    assert "UMA vLLM baseline" in build
    assert "free-memory snapshot" in build


def test_installer_defaults_to_runtime_artifacts_not_source_or_aiter() -> None:
    installer = _text("scripts/install.sh")
    assert "\nSYNC_SOURCES=0\n" in installer
    assert "--sync-sources" in installer
    assert "INCLUDE_AITER=0" in installer
    assert "--include-aiter" in installer
    assert "pull_services=(vllm sglang quark)" in installer
    assert 'docker compose pull "${pull_services[@]}"' in installer


def test_installer_explains_pull_denied_instead_of_raw_401() -> None:
    # A private/unpublished GHCR package surfaces as an opaque "denied"/401 from
    # `docker compose pull`. The installer must translate that for a friend.
    installer = _text("scripts/install.sh")
    assert "github.com/orgs/HawgAuto/packages" in installer
    assert "unauthorized" in installer or "denied" in installer
    assert "docker login ghcr.io" in installer


def test_readiness_status_before_initialize_is_explained_not_traceback() -> None:
    # `haloloom <fw> readiness status` on a fresh workspace must not dump a
    # Python traceback; the entrypoint tells the friend to run `initialize`.
    entrypoint = _text("docker/ecosystem/workbench-entrypoint")
    assert "readiness-control/READINESS-EPOCH.json" in entrypoint
    assert "readiness initialize" in entrypoint
    readme = _text("README.md")
    assert "readiness initialize" in readme
    assert "agent-check" in readme


def test_optimize_front_door_is_gfx1151_aware_and_gated() -> None:
    # The friend-facing `haloloom <fw> optimize` path must reach Magpie's
    # radeon8060s runners. That needs (a) the board registered in Hyperloom,
    # (b) gfx1151 -> radeon8060s in Magpie, and (c) a bounded real `optimize`
    # run on gfx1151 recorded as a receipt bound in the manifest.
    comp = json.loads(_text("manifests/components.json"))
    assert comp["components"]["hyperloom"]["board_support"]["radeon8060s"] == "gfx1151"
    assert comp["components"]["magpie"]["runner_selection"]["gfx1151"] == "radeon8060s"
    gate = comp["qualification"]["optimize_front_door_gate"]
    receipt = json.loads(_text(gate["receipt"]))
    assert hashlib.sha256(_bytes(gate["receipt"])).hexdigest() == gate["receipt_sha256"]
    assert receipt["status"] == "PASS"
    assert receipt["gpu_type"] == "radeon8060s" and receipt["gfx_arch"] == "gfx1151"
    assert receipt["benchmark_script"] in ("vllm_radeon8060s.sh", "sglang_radeon8060s.sh")
    assert receipt["baseline"]["completed"] is True
    assert receipt["kfd_clear_post"] is True and receipt["gpu_lock_released"] is True
    # The gate runs the real CLI front door, not the readiness controller.
    assert receipt["argv"][0:2] == ["inference_optimizer", "optimize"]
    assert "--gpu-type" in receipt["argv"] and "radeon8060s" in receipt["argv"]
    readme = _text("README.md")
    assert "--gpu-type radeon8060s" in readme


def test_kernel_agent_env_file_only_carries_allowlisted_keys() -> None:
    # Hyperloom's preflight re-reads kernel-agent.env.sh through a strict
    # allowlist and prints a WARNING per rejected key. The workbench entrypoint
    # exports its full environment to the process anyway, so the file must
    # contain only keys Hyperloom's loader accepts -- otherwise every friend
    # run starts with a wall of spurious warnings.
    allowlisted = {
        "GEAK_CLAUDE_BIN", "GEAK_E2E_RUNNER", "GEAK_ROOT", "HYPERLOOM_KERNEL_AGENT_ROOT",
        "HYPERLOOM_ROOT", "HYPERLOOM_RUNTIME_DIR", "INFERENCE_OPTIMIZER_FRAMEWORK_SOURCE_ROOTS",
        "INFERENCEX_PATH", "KERNEL_AGENT_ENV", "KERNEL_AGENT_ROOT", "MAGPIE_PATH", "MAGPIE_PYTHON",
        "TRACELENS_ROOT", "USER_DATA_PATH",
    }
    entrypoint = _text("docker/ecosystem/workbench-entrypoint")
    block = entrypoint.split("for name in \\", 1)[1].split("; do", 1)[0]
    written = set(block.replace("\\", " ").split())
    assert written <= allowlisted, sorted(written - allowlisted)
    for rejected in ("PATH", "PYTHONPATH", "FORGE_AGENT_BACKEND", "FORGE_AGENT_CLI",
                     "GEAK_AGENT_PROFILE", "HYPERLOOM_CACHE_DIR", "HYPERLOOM_DEPS_ROOT",
                     "FRAMEWORK_AGENT_ROOT"):
        assert rejected not in written, rejected
    # Codex/Hermes bins are exported to the process, not persisted into the
    # file, because Hyperloom's allowlist only knows GEAK_CLAUDE_BIN.
    assert "printf 'export GEAK_CODEX_BIN" not in entrypoint
    assert "printf 'export GEAK_HERMES_BIN" not in entrypoint


def test_codex_agent_uses_cli_login_when_present_and_no_key_is_set() -> None:
    """Codex subscription users: `codex login` on the host is the credential.

    HaloLoom mounts ~/.codex read-only at $CODEX_HOME. If that login exists and
    the operator set no API key/base URL, the workbench opts the Orchestrator
    into Hyperloom's Codex ``native_oauth`` mode (which mirrors KernelForge's).
    A key in the environment wins and keeps upstream gateway semantics, so the
    mode can never be selected against the operator's explicit configuration.
    """
    entrypoint = _text("docker/ecosystem/workbench-entrypoint")
    codex_case = entrypoint[entrypoint.index("  codex)") : entrypoint.index("  hermes)")]
    assert '[[ -f "$CODEX_HOME/auth.json" && -z "${OPENAI_API_KEY:-}${OPENAI_BASE_URL:-}" ]]' in codex_case
    assert 'native_home=/tmp/haloloom-codex-home' in codex_case
    assert 'install -m 0600 "$CODEX_HOME/auth.json" "$native_home/auth.json"' in codex_case
    assert "export INFERENCE_OPTIMIZER_CODEX_AUTH_MODE=native_oauth" in codex_case
    assert 'export INFERENCE_OPTIMIZER_CODEX_HOME="$native_home"' in codex_case
    # The image intentionally has no bubblewrap. Docker is the external sandbox,
    # so every Codex role must bypass the unavailable inner sandbox instead of
    # looping on a fail-closed `workspace-write` capability error.
    assert "export HYPERLOOM_CODEX_EXTERNAL_SANDBOX=1" in codex_case
    assert "export HYPERLOOM_CODEX_SANDBOX_MODE=bypass" in codex_case
    assert "export GEAK_CODEX_EXTERNAL_SANDBOX=1" in codex_case
    assert "/workspace" not in codex_case
    # Never forces a model, never manufactures a key, never touches other agents.
    assert "CODEX_MODEL=" not in codex_case
    assert "OPENAI_API_KEY=" not in codex_case
    assert "hermes" not in codex_case.lower()

    compose = _text("compose.yaml")
    assert "${CODEX_HOME_HOST}:/home/haloloom/.codex:ro" in compose



def test_image_builder_uses_public_source_current_overlay() -> None:
    builder = _text("scripts/build_images.sh")
    assert 'exec python3 "$ROOT/scripts/build_release_inputs.py" "$@"' in builder
    assert "hyperloom-vllm-v027-rocm10" not in builder
    assert "hyperloom-sglang-v0515-rocm10" not in builder
    assert "require_image_id" not in builder
    recipe = _text("docker/source-current/Dockerfile")
    assert "ARG BASE_IMAGE" in recipe
    assert "FROM ${BASE_IMAGE}" in recipe
    assert "COPY --chown=1000:1000 dist/source-current/ /opt/haloloom/source-current/" in recipe
    assert "/opt/haloloom/source-current/apply-and-verify.py" in recipe
    assert "/opt/haloloom-agent/bin/python3 -m pip install --no-index --no-deps" in recipe
    assert 'haloloom.promotion_authority="false"' in recipe


def test_raw_physical_attempts_are_not_publishable() -> None:
    ignore = _text(".gitignore")
    assert "qualification/full-golden-v0.1.0/" in ignore
    assert "qualification/final-v0.1.0/" in ignore
    assert "qualification/receipts/" not in ignore


def test_generated_friend_runtime_state_is_not_publishable() -> None:
    ignore = _text(".gitignore")
    for path in (
        ".haloloom-agent-plugins/",
        "artifacts/",
        "components/",
        "workspace/",
    ):
        assert path in ignore


def test_final_readiness_authority_is_bundled_for_friend_control() -> None:
    expected = {
        "qualification/readiness/FINAL-CLOSEOUT.json": "593ac3978c40bf0c2612e1ddd9a20cf77ed9bd0801a5e7292d6a283b94cff3db",
        "qualification/readiness/FUNCTIONAL-TARGET-MATRIX-SEALED.json": "189d3f37808efd2d07e019802f8e8983c283bbbce66f79889a0dac3152840a4e",
        "qualification/readiness/SUPPORT-BOUNDARIES.md": "3446bbb4637867349be48990dbf2b7b0ac44fdcdcb2b70221d2f0f7a32af905f",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
    closeout = json.loads(_text("qualification/readiness/FINAL-CLOSEOUT.json"))
    assert closeout["status"] == "PASS_FUNCTIONALLY_COMPLETE_PRODUCTION_READY_NOT_ACTIVATED"
    matrix = json.loads(_text("qualification/readiness/FUNCTIONAL-TARGET-MATRIX.json"))
    assert matrix["status"] == "PASS"
    assert matrix["target_count"] == 23
    assert matrix["registry_sha256"] == "987bab827d8d8cca082cb00d9320c2d4d401d85673ca771fec280c0a73950f09"
    assert matrix["promotion_authority"] is False
    sealed = json.loads(_text("qualification/readiness/FUNCTIONAL-TARGET-MATRIX-SEALED.json"))
    assert matrix["targets"] == sealed["targets"]
    assert matrix["registry_id"] == sealed["registry_id"]
    handoff = json.loads(_text("qualification/readiness/PUBLIC-LINEAGE-HANDOFF.json"))
    assert handoff["status"] == "PASS_PUBLIC_LINEAGE_EQUIVALENT_TARGET_ROSTER"
    assert handoff["sealed_functional_proof_sha256"] == expected[
        "qualification/readiness/FUNCTIONAL-TARGET-MATRIX-SEALED.json"
    ]
    assert handoff["runtime_semantics_changed"] is False
    assert handoff["production_activated"] is False
    assert handoff["promotion_authority"] is False
    component = json.loads(_text("manifests/components.json"))["components"]["hyperloom"]
    assert component["public_registry_sha256"] == matrix["registry_sha256"]
    assert component["public_functional_proof_sha256"] == hashlib.sha256(
        (ROOT / "qualification/readiness/FUNCTIONAL-TARGET-MATRIX.json").read_bytes()
    ).hexdigest()
    assert component["sealed_functional_proof_sha256"] == expected[
        "qualification/readiness/FUNCTIONAL-TARGET-MATRIX-SEALED.json"
    ]
    assert component["public_lineage_handoff_sha256"] == hashlib.sha256(
        (ROOT / "qualification/readiness/PUBLIC-LINEAGE-HANDOFF.json").read_bytes()
    ).hexdigest()
    dockerfile = _text("docker/ecosystem/Dockerfile")
    assert "COPY qualification/readiness /opt/haloloom/readiness" in dockerfile
    entrypoint = _text("docker/ecosystem/workbench-entrypoint")
    assert "hyperloom.orchestrator.production_readiness" in entrypoint
    assert "  readiness)" in entrypoint


def test_final_quark_and_aiter_receipts_are_bound_and_claim_limited() -> None:
    images = json.loads(_text("manifests/components.json"))["images"]
    for name in ("quark", "aiter_tools"):
        row = images[name]
        path = ROOT / row["qualification_receipt"]
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == row["qualification_receipt_sha256"]
        )
        assert row["physical_arch"] == "gfx1151"
        assert row["production_activated"] is False
    quark = json.loads(_text(images["quark"]["qualification_receipt"]))
    assert quark["claim_boundary"]["fresh_ptq_export"] is False
    assert quark["claim_boundary"]["candidate_quality_accepted"] is False
    assert quark["prior_ptq_lifecycle"]["quality"]["status"] == "REJECT"
    aiter = json.loads(_text("qualification/receipts/aiter-final-bounded-v0.1.0.json"))
    assert aiter["claim_boundary"]["module_sample_jit_qualified"] is True
    assert aiter["claim_boundary"]["module_sample_operation_qualified"] is False
    assert aiter["claim_boundary"]["aiter_attention_qualified"] is False
    assert aiter["promotion_authority"] is False


def test_current_lowbit_route_status_binds_immutable_final_receipts() -> None:
    status = json.loads(_text("qualification/route-status-v0.1.0.json"))
    assert status["status"] == "W4A8_FINAL_FRAMEWORK_PASS_OTHER_ROUTES_DIRECT_ONLY"
    for binding in status["immutable_inputs"].values():
        if "path" not in binding:
            continue
        path = ROOT / binding["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["sha256"]
    assert status["routes"]["gfx1151-w4a8"]["vllm_final_image"] == "PASS"
    assert status["routes"]["gfx1151-w4a8"]["sglang_final_image"] == "PASS"
    for route, row in status["routes"].items():
        assert row["direct_physical"] == "PASS"
        assert row["performance_qualified"] is False
        if route != "gfx1151-w4a8":
            assert row["vllm_final_image"] == "DIRECT_ONLY_FRAMEWORK_PENDING"
            assert row["sglang_final_image"] == "DIRECT_ONLY_FRAMEWORK_PENDING"
