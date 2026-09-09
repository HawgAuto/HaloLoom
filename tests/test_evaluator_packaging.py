"""The native evaluator must be installed offline, not pip-installed at run time."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_shared_image_installs_hash_locked_eval_before_task_namespace_repair():
    text = (ROOT / "docker/source-current/Dockerfile").read_text()
    shared = text.split("FROM source-current AS vllm", 1)[0]
    install = shared.index("pip install --no-cache-dir --no-index --no-deps --require-hashes")
    assert install < shared.index("qualify_eval_task_namespaces.py --report")
    assert "--find-links /opt/haloloom/source-current/evaluation-wheels" in shared
    assert "-r /opt/haloloom/source-current/evaluation-wheels/requirements.lock" in shared


def test_evaluator_lock_does_not_replace_serving_or_rocm_packages():
    lock = ROOT / "docker/evaluation/requirements.lock"
    assert lock.is_file(), "the supported image recipe needs an immutable evaluator lock"
    names = []
    for line in lock.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
        assert match, line
        names.append(match[1].lower().replace("_", "-"))
    assert len(names) == len(set(names))
    assert "lm-eval" in names
    protected = {"torch", "triton", "transformers", "vllm", "sglang", "amd-quark", "datasets", "numpy"}
    assert not protected.intersection(names)
    assert not any(name.startswith("rocm") for name in names)
