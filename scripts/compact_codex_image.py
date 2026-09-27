#!/usr/bin/env python3
"""Compact a *local, unpromoted* Codex/AMD candidate into a source-bound OCI layer.

FROM scratch COPY --from=resolved / / copies only the resolved filesystem,
not the inherited image's deleted lower layers. Preserve and check the image
config explicitly; a compacted image is a NEW runtime epoch and still needs
physical qualification before promotion.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def image(ref: str) -> dict:
    return json.loads(subprocess.check_output(["docker", "image", "inspect", ref], text=True))[0]


def dockerfile(source: str, old: dict, verify_ecosystem: bool, extra_labels: dict[str, str]) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9._:/-]+", source):
        raise ValueError("Unsafe image reference")
    c = old["Config"]
    if c.get("Healthcheck") or c.get("OnBuild") or c.get("Volumes"):
        raise ValueError("Unsupported inherited HEALTHCHECK, ONBUILD or VOLUME")
    labels = dict(c.get("Labels") or {})
    if labels.get("haloloom.promotion_authority") != "false":
        raise ValueError("Only unpromoted local candidates may be compacted")
    labels.update(extra_labels)
    if labels.get("haloloom.promotion_authority") != "false":
        raise ValueError("Compaction cannot grant promotion authority")
    labels["haloloom.oci_compacted"] = "true"
    labels["haloloom.oci_compacted_from"] = old["Id"]
    workdir = c.get("WorkingDir")
    if workdir and not re.fullmatch(r"/[a-zA-Z0-9_./-]*", workdir):
        raise ValueError("Unsafe working directory")
    lines = ["# syntax=docker/dockerfile:1.7", f"FROM {source} AS resolved", "USER root",
             "RUN set -eu; \\",
             "    rm -f /opt/haloloom/source-current/native-agent-source/codex-amd-source-rust-v0.153.4.tar.gz; \\",
             "    test \"$(/opt/haloloom/codex-amd/bin/codex --version)\" = 'codex-cli 0.156.1'; \\",
             "    test ! -e /opt/haloloom/source-current/native-agent-source/codex-amd-source-rust-v0.153.4.tar.gz"]

    if verify_ecosystem:
        lines[-1] += "; " + chr(92)  # append a command to the RUN directive
        lines.append("    /opt/venv/bin/python3 /opt/haloloom/verify_ecosystem.py")
    lines += ["", "FROM scratch", "COPY --from=resolved / /"]
    for env in c.get("Env") or []:
        key, sep, value = env.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key):
            raise ValueError(f"Unsafe environment key {key!r}")
        if any(x in value for x in "\n\r\0"):
            raise ValueError(f"Unsafe environment value for {key}")
        lines.append(f"ENV {key}={json.dumps(value)}")
    for key, value in sorted(labels.items()):
        if any(x in key + value for x in "\n\r\0"):
            raise ValueError(f"Unsafe label {key!r}")
        lines.append(f"LABEL {key}={json.dumps(value)}")
    for port in sorted(c.get("ExposedPorts") or {}):
        lines.append(f"EXPOSE {port}")
    if c.get("User"):
        lines.append(f"USER {c['User']}")
    # BuildKit emits a filesystem layer for non-root-path WORKDIR; restore
    # its metadata using a one-instruction legacy build from the copied image.
    for key in ("Shell", "Entrypoint", "Cmd"):
        if c.get(key) is not None:
            lines.append(f"{key.upper()} {json.dumps(c[key])}")
    if c.get("StopSignal"):
        lines.append(f"STOPSIGNAL {c['StopSignal']}")
    return "\n".join(lines) + "\n"


def verify(source: dict, target: dict, extra_labels: dict[str, str]) -> None:
    if len(target["RootFS"]["Layers"]) != 1:
        raise RuntimeError("Compacted image must have exactly one filesystem layer")
    a, b = source["Config"], target["Config"]
    for key in ("Env", "User", "WorkingDir", "Entrypoint", "Cmd", "Shell", "ExposedPorts", "Volumes", "StopSignal"):
        if (a.get(key) or None) != (b.get(key) or None):
            raise RuntimeError(f"Compacted image config drift: {key}")
    labels = dict(a.get("Labels") or {})
    labels.update(extra_labels)
    labels["haloloom.oci_compacted"] = "true"
    labels["haloloom.oci_compacted_from"] = source["Id"]
    if labels != (b.get("Labels") or {}):
        raise RuntimeError("Compacted image label drift")


def restore_workdir(staging: str, target: str, workdir: str) -> None:
    # BuildKit adds a WORKDIR filesystem layer; Docker's legacy builder
    # preserves the one-layer rootfs when that directory already exists.
    # Unlike docker commit, this retains the inherited SHELL image config.
    # Metadata-only stage: no network, pulls, or RUN instructions.
    with tempfile.TemporaryDirectory(prefix="haloloom-workdir-") as tmp:
        Path(tmp, "Dockerfile").write_text(f"FROM {image(staging)['Id']}\nWORKDIR {workdir}\n")
        subprocess.run(["docker", "build", "--pull=false", "--network=none", "-t", target, tmp],
                       check=True, env={**os.environ, "DOCKER_BUILDKIT": "0"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Exact inspected local image tag")
    parser.add_argument("target", help="NEW compacted local tag")
    parser.add_argument("--verify-ecosystem", action="store_true")
    parser.add_argument("--recipe-out", type=Path, help="Persist the exact generated Dockerfile")
    parser.add_argument("--label", action="append", default=[], help="Explicit key=value label override")
    args = parser.parse_args()
    old = image(args.source)
    if subprocess.run(["docker", "image", "inspect", args.target], capture_output=True).returncode == 0:
        raise SystemExit("Refusing to overwrite an existing tag")
    workdir = old["Config"].get("WorkingDir")
    staging = args.target + "-workdir-pending" if workdir else args.target
    if staging != args.target and subprocess.run(["docker", "image", "inspect", staging], capture_output=True).returncode == 0:
        raise SystemExit("Refusing to overwrite an existing staging tag")
    if shutil.disk_usage("/").free < 2 * old["Size"]:
        raise SystemExit("Insufficient disk space for a new resolved image layer and workspace reserve")
    extra = dict(item.split("=", 1) for item in args.label)
    recipe = dockerfile(args.source, old, args.verify_ecosystem, extra)
    if args.recipe_out:
        if args.recipe_out.exists():
            raise SystemExit("Refusing to overwrite an existing Dockerfile receipt")
        args.recipe_out.parent.mkdir(parents=True, exist_ok=True)
        postbuild = f"# postbuild=DOCKER_BUILDKIT=0 docker build --network=none --pull=false (FROM staging image ID; WORKDIR {workdir}) -> {args.target}\n" if workdir else ""
        args.recipe_out.write_text(f"# pinned_source_image_id={old['Id']}\n" + postbuild + recipe)
    with tempfile.TemporaryDirectory(prefix="haloloom-compact-") as tmp:
        Path(tmp, "Dockerfile").write_text(recipe)
        # Keep an exact recipe receipt outside this temporary context for a release packet.
        command = ["docker", "build", "--pull=false", "--network=none", "--progress=plain",
                   "-t", staging, tmp]
        subprocess.run(command, check=True)
    if image(args.source)["Id"] != old["Id"]:
        raise RuntimeError("Source tag changed while compaction was running")
    if workdir:
        if len(image(staging)["RootFS"]["Layers"]) != 1:
            raise RuntimeError("Staging image must have exactly one filesystem layer")
        restore_workdir(staging, args.target, workdir)
    new = image(args.target)
    verify(old, new, extra)
    if workdir:
        subprocess.run(["docker", "image", "rm", staging], check=True)
    print(json.dumps({"source": old["Id"], "target": new["Id"], "tag": args.target,
                      "rootfs_layers": len(new["RootFS"]["Layers"]), "bytes": new["Size"]}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"compaction failed: {exc}", file=sys.stderr)
        sys.exit(1)
