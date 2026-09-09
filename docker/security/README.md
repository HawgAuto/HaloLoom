# Opt-in native Codex sandbox policy

This named policy enables the nested user/network/mount namespaces that the
selected Codex runtime's bundled bubblewrap requires. It is **not** an unconfined
profile, does not add outer-container capabilities, and does not change host
AppArmor or user-namespace sysctls. Codex's workspace-only write boundary remains
mandatory for candidate review.

The AppArmor profile derives from the pinned Moby template with explicit
`userns`, `mount`, and `pivot_root` permission. It retains the unrelated proc,
sysfs, AF_ALG and AF_VSOCK denials. ABI 4 declares UNIX sockets explicitly.
The seccomp profile retains the pinned Docker-default rules and adds only
`clone` with `CLONE_NEWUSER`, `unshare`, `setns`, `mount`, `umount2`, and
`pivot_root`. The outer container must retain `--cap-drop ALL` and
`--security-opt no-new-privileges=true`. No privileged container is required.

## Explicit host installation

Review and approve this named host-policy exception first. Do not overwrite an
administrator-modified profile without comparing it with the checked-in file.
From the HaloLoom repository root, validate and install this profile:

```bash
apparmor_parser --skip-kernel-load --skip-read-cache docker/security/haloloom-codex-native.apparmor
sudo install -o root -g root -m 0644 docker/security/haloloom-codex-native.apparmor /etc/apparmor.d/haloloom-codex-native
sudo apparmor_parser --replace --skip-read-cache /etc/apparmor.d/haloloom-codex-native
```

Apply **only to the intended native-agent container**:

```text
--cap-drop ALL
--security-opt no-new-privileges=true
--security-opt apparmor=haloloom-codex-native
--security-opt seccomp=/absolute/checkout/docker/security/haloloom-codex-native.seccomp.json
```

Do not replace these with `--privileged`, `apparmor=unconfined`, or
`seccomp=unconfined`. Keep the review sandbox set to `workspace-write`; do not
switch it to bypass when capability checks fail. A host without the necessary
AppArmor/namespace support must receive an explicit compatibility diagnostic,
not an automatic change to global security settings.

## Verification and limits

Require the actual selected runtime's namespace probe and an actual Codex
sandbox write test: a parent-writable output directory must remain writable,
while a separate parent-writable directory outside the allowed workspace must
reject writes. Confirm zero effective capabilities, `NoNewPrivs=1`, unchanged
host-global controls, and cleanup. Merely finding `bwrap` or compiling the policy
is insufficient.

The current policy is opt-in. Product installer/launcher adoption and final-image
verification are separate release requirements; this document does not claim
that the default installation already activates the policy. See `UPSTREAM.json`
and `LICENSE.moby` for the pinned inputs and attribution.
