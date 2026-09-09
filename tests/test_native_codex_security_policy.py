"""The opt-in nested sandbox policy preserves Docker's unrelated denials."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1] / 'docker/security'


def test_apparmor_is_named_and_enforcing_not_unconfined():
    text = (ROOT / 'haloloom-codex-native.apparmor').read_text()
    assert 'profile "haloloom-codex-native"' in text
    assert 'flags=(attach_disconnected,mediate_deleted)' in text
    assert 'flags=(unconfined)' not in text
    assert 'complain' not in text
    assert '\n  userns,' in text
    assert '\n  mount,' in text
    assert '\n  pivot_root,' in text
    assert 'deny @{PROC}/sysrq-trigger rwklx,' in text
    assert 'deny /sys/kernel/security/** rwklx,' in text
    assert 'deny network alg,' in text
    assert 'deny network vsock,' in text


def test_seccomp_preserves_base_and_limits_additions():
    base = json.loads((ROOT / 'moby-seccomp-base.json').read_text())
    actual = json.loads((ROOT / 'haloloom-codex-native.seccomp.json').read_text())
    assert actual['defaultAction'] == 'SCMP_ACT_ERRNO'
    assert {k:v for k,v in actual.items() if k!='syscalls'} == {k:v for k,v in base.items() if k!='syscalls'}
    assert actual['syscalls'][:len(base['syscalls'])] == base['syscalls']
    extra = actual['syscalls'][len(base['syscalls']):]
    assert {n for rule in extra for n in rule['names']} == {
        'clone', 'unshare', 'setns', 'mount', 'umount2', 'pivot_root'}
    assert all(rule['action'] == 'SCMP_ACT_ALLOW' for rule in extra)
    clone = next(rule for rule in extra if 'clone' in rule['names'])
    assert clone['args'] == [{'index':0,'value':0x10000000,
                             'valueTwo':0x10000000,'op':'SCMP_CMP_MASKED_EQ'}]


def test_policy_provenance_is_content_bound():
    import hashlib
    receipt = json.loads((ROOT / 'UPSTREAM.json').read_text())
    assert len(receipt['moby_profiles_commit']) == 40
    for name,digest in receipt['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
