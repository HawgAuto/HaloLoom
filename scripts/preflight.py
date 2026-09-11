#!/usr/bin/env python3
"""Fail-closed HaloLoom host preflight for Strix Halo."""

from __future__ import annotations

import argparse
import fcntl
import grp
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

MIN_DISK_BYTES = 25 * 1024**3
LOCK_PATH = Path("/run/lock/hermes-vllm-gfx1151.lock")


def assess(probe: dict[str, Any], *, allow_busy: bool) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not probe.get("docker"):
        errors.append("Docker CLI/daemon is unavailable")
    if not probe.get("compose"):
        errors.append("Docker Compose v2 is unavailable")
    if not probe.get("kfd"):
        errors.append("/dev/kfd is missing")
    if not probe.get("dri"):
        errors.append("/dev/dri is missing")
    if probe.get("arch") != "gfx1151":
        errors.append(f"native gfx1151 was not detected (got {probe.get('arch')!r})")
    if probe.get("hsa_override") is not None:
        errors.append("HSA_OVERRIDE_GFX_VERSION must be unset, not spoofed")
    if int(probe.get("disk_free_bytes") or 0) < MIN_DISK_BYTES:
        errors.append(
            "at least 25 GiB of free storage is required for the core image set"
        )
    if probe.get("video_gid") is None or probe.get("render_gid") is None:
        errors.append("host video/render groups must exist")
    else:
        memberships = set(probe.get("member_gids") or [])
        missing = [
            name
            for name, gid in (
                ("video", probe["video_gid"]),
                ("render", probe["render_gid"]),
            )
            if gid not in memberships
        ]
        if missing and int(probe.get("uid") or -1) != 0:
            errors.append("current user is not a member of: " + ", ".join(missing))
    if not probe.get("lock_available"):
        errors.append(f"GPU lease is already held: {LOCK_PATH}")
    owners = sorted({int(pid) for pid in probe.get("kfd_pids") or []})
    if owners:
        message = f"/dev/kfd already has owner PID(s): {', '.join(map(str, owners))}"
        if allow_busy:
            warnings.append(message + " (allowed for inspection only)")
        else:
            errors.append(message)
    if probe.get("fuser_error"):
        errors.append(f"could not determine /dev/kfd ownership: {probe['fuser_error']}")

    return {
        "schema_version": 1,
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "probe": probe,
    }


def release_version() -> str:
    """Use this checkout's release manifest, never a stale installer default."""
    manifest = Path(__file__).resolve().parents[1] / "manifests" / "components.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    version = data.get("release") if isinstance(data, dict) else None
    number = r"(?:0|[1-9][0-9]*)"
    if not isinstance(version, str) or not re.fullmatch(
        rf"v{number}\.{number}\.{number}(?:-rc{number})?", version
    ):
        raise ValueError("components manifest release must be vX.Y.Z or vX.Y.Z-rcN")
    return version


def render_env(probe: dict[str, Any]) -> str:
    home = str(probe["home"])
    cwd = str(probe["cwd"])
    values = {
        "HALOLOOM_VERSION": release_version(),
        "HOST_UID": int(probe["uid"]),
        "HOST_GID": int(probe["gid"]),
        "VIDEO_GID": int(probe["video_gid"]),
        "RENDER_GID": int(probe["render_gid"]),
        "HF_HOME": f"{home}/.cache/huggingface",
        "HALOLOOM_WORKSPACE": f"{cwd}/workspace",
        "HERMES_HOME_HOST": f"{home}/.hermes",
        "CODEX_HOME_HOST": f"{home}/.codex",
    }
    rows = []
    for key, value in values.items():
        if isinstance(value, int):
            rows.append(f"{key}={value}")
        else:
            if "\n" in value or "\r" in value:
                raise ValueError(f"newline is not valid in {key}")
            rendered = (
                value
                if re.fullmatch(r"[A-Za-z0-9_./:@+-]+", value)
                else json.dumps(value)
            )
            rows.append(f"{key}={rendered}")
    return "\n".join(rows) + "\n"


def _run(command: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, text=True, capture_output=True, timeout=timeout, check=False
    )


def _detect_arch() -> str | None:
    rocminfo = shutil.which("rocminfo")
    if rocminfo:
        result = _run([rocminfo])
        match = re.search(r"\bgfx[0-9a-z]+\b", result.stdout, re.IGNORECASE)
        if result.returncode == 0 and match:
            return match.group(0).lower()
    for properties in sorted(
        Path("/sys/class/kfd/kfd/topology/nodes").glob("*/properties")
    ):
        try:
            text = properties.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^gfx_target_version\s+(\d+)\s*$", text, re.MULTILINE)
        if match and match.group(1) == "110501":
            return "gfx1151"
    return None


def _group_id(name: str) -> int | None:
    try:
        return grp.getgrnam(name).gr_gid
    except KeyError:
        return None


def _lock_available() -> bool:
    try:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_PATH.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(handle, fcntl.LOCK_UN)
        return True
    except (BlockingIOError, OSError):
        return False


def live_probe() -> dict[str, Any]:
    docker_path = shutil.which("docker")
    docker = bool(docker_path and _run([docker_path, "info"]).returncode == 0)
    compose = bool(
        docker_path and _run([docker_path, "compose", "version"]).returncode == 0
    )

    fuser_error = None
    kfd_pids: list[int] = []
    fuser = shutil.which("fuser")
    if fuser and Path("/dev/kfd").exists():
        result = _run([fuser, "/dev/kfd"])
        if result.returncode == 0:
            kfd_pids = [
                int(value) for value in result.stdout.split() if value.isdigit()
            ]
        elif result.returncode != 1:
            fuser_error = (
                result.stderr or result.stdout
            ).strip() or f"exit {result.returncode}"
    elif not fuser:
        fuser_error = "fuser command is unavailable"

    usage = shutil.disk_usage(Path.cwd())
    video_gid = _group_id("video")
    render_gid = _group_id("render")
    return {
        "docker": docker,
        "compose": compose,
        "kfd": Path("/dev/kfd").exists(),
        "dri": Path("/dev/dri").is_dir(),
        "arch": _detect_arch(),
        "hsa_override": os.environ.get("HSA_OVERRIDE_GFX_VERSION")
        if "HSA_OVERRIDE_GFX_VERSION" in os.environ
        else None,
        "disk_free_bytes": usage.free,
        "kfd_pids": kfd_pids,
        "fuser_error": fuser_error,
        "video_gid": video_gid,
        "render_gid": render_gid,
        "member_gids": sorted(set(os.getgroups()) | {os.getgid()}),
        "lock_available": _lock_available(),
        "uid": os.getuid(),
        "gid": os.getgid(),
        "home": str(Path.home()),
        "cwd": str(Path.cwd()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-busy",
        action="store_true",
        help="report existing KFD owners as a warning",
    )
    parser.add_argument("--write-env", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    probe = live_probe()
    report = assess(probe, allow_busy=args.allow_busy)
    if args.write_env and report["passed"]:
        try:
            env_text = render_env(probe)
        except (OSError, ValueError) as error:
            report["passed"] = False
            report["errors"].append(f"cannot resolve release configuration: {error}")
        else:
            args.write_env.write_text(env_text, encoding="utf-8")
            report["env_file"] = str(args.write_env.resolve())
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for warning in report["warnings"]:
            print(f"WARN: {warning}")
        for error in report["errors"]:
            print(f"ERROR: {error}")
        print(
            "HALOLOOM_PREFLIGHT_OK" if report["passed"] else "HALOLOOM_PREFLIGHT_FAILED"
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
