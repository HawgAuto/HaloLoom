"""Register the image's bundled AMD SMI without admitting ambient PYTHONPATH.

Run only at image assembly (or verify-only in that immutable image). No package
installation, network, AMD SMI import, device probe, or framework mutation occurs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sysconfig

RELATIVE_SDK = '_rocm_sdk_core/share/amd_smi'
PTH_NAME = 'haloloom_bundled_amdsmi.pth'


def install_bundled_amdsmi(purelib: Path, *, verify_only: bool = False) -> dict:
    purelib = Path(purelib).resolve(strict=True)
    sdk = purelib / '_rocm_sdk_core'
    if sdk.is_symlink():
        raise ValueError('Bundled AMD SMI symlink provenance rejected')
    if not sdk.exists():
        return {'status': 'not_applicable_no_modular_sdk', 'purelib': str(purelib)}
    package = purelib / RELATIVE_SDK / 'amdsmi'
    for path in (purelib / RELATIVE_SDK, package, package / '__init__.py'):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError('Bundled AMD SMI symlink provenance rejected')
    if not (package / '__init__.py').is_file():
        raise ValueError('Bundled AMD SMI is missing from the installed modular SDK')
    files = {}
    def walk_error(error):
        raise error
    for directory, directories, names in os.walk(package, followlinks=False, onerror=walk_error):
        for name in directories + names:
            path = Path(directory) / name
            if path.is_symlink() or path.resolve() != path:
                raise ValueError(f'Bundled AMD SMI symlink provenance rejected: {path}')
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                files[str(path.relative_to(purelib))] = hashlib.sha256(path.read_bytes()).hexdigest()
    pth = purelib / PTH_NAME
    expected = (RELATIVE_SDK + '\n').encode()
    if pth.is_symlink():
        raise ValueError('AMD SMI registration symlink rejected')
    if pth.exists():
        if not pth.is_file() or pth.read_bytes() != expected:
            raise ValueError('Foreign AMD SMI registration will not be overwritten')
    elif verify_only:
        raise ValueError('AMD SMI registration is missing')
    else:
        fd = os.open(pth, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
    return {'status': 'registered', 'purelib': str(purelib), 'pth': str(pth),
            'pth_sha256': hashlib.sha256(expected).hexdigest(), 'sdk_files': dict(sorted(files.items()))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = install_bundled_amdsmi(Path(sysconfig.get_path('purelib')), verify_only=args.verify_only)
    if args.report:
        if args.verify_only:
            if json.loads(args.report.read_text()) != result:
                raise ValueError('Bundled AMD SMI image receipt mismatch')
        else:
            args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
