"""Qualify legacy GSM8K dataset IDs without changing task semantics."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

LEGACY_GSM8K = re.compile(rb"""(?m)^(dataset_path:[ \t]*)(['"]?)gsm8k\2(?=[ \t]*(?:#|\r?$))""")


def qualify_gsm8k_tasks(lm_eval_root: Path) -> list[dict[str, str]]:
    changes = []
    for path in sorted((lm_eval_root / 'tasks').rglob('*.yaml')):
        before = path.read_bytes()
        after = LEGACY_GSM8K.sub(lambda m: m[1] + m[2] + b'openai/gsm8k' + m[2], before)
        if after == before:
            continue
        if path.is_symlink():
            raise ValueError(f'Refusing to rewrite symlinked task: {path}')
        path.write_bytes(after)
        changes.append({'path': str(path.relative_to(lm_eval_root)),
                        'before_sha256': hashlib.sha256(before).hexdigest(),
                        'after_sha256': hashlib.sha256(after).hexdigest()})
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    spec = importlib.util.find_spec('lm_eval')
    if spec is None:
        report = {'status': 'lm_eval_not_installed', 'changes': []}
    else:
        assert spec.origin is not None
        root = Path(spec.origin).parent
        report = {'status': 'processed', 'module_root': str(root),
                  'changes': qualify_gsm8k_tasks(root)}
    serialized = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.write_text(serialized)
    print(serialized, end='')


if __name__ == '__main__':
    main()
