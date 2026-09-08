"""New namespace regressions; pre-existing HaloLoom tests stay unchanged."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/qualify_eval_task_namespaces.py'


class EvalTaskNamespaces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='haloloom-eval-namespace-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.task = self.root / 'tasks/gsm8k/gsm8k.yaml'
        self.task.parent.mkdir(parents=True)

    def repair(self):
        self.assertTrue(SCRIPT.is_file(), 'namespace repair is not implemented')
        spec = importlib.util.spec_from_file_location('namespace_repair', SCRIPT)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.qualify_gsm8k_tasks(self.root)

    def test_only_dataset_identifier_changes(self):
        original = (b'task: gsm8k\ndataset_path: gsm8k\ndataset_name: main\n'
                    b'doc_to_text: "Question: {{question}}\\nAnswer:"\n'
                    b'metric_list: [{metric: exact_match, aggregation: mean}]\n'
                    b'generation_kwargs: {temperature: 0.0}\nnum_fewshot: 5\n')
        self.task.write_bytes(original)
        changes = self.repair()
        self.assertEqual(self.task.read_bytes(), original.replace(b'dataset_path: gsm8k', b'dataset_path: openai/gsm8k'))
        self.assertEqual(len(changes), 1)
        self.assertNotEqual(changes[0]['before_sha256'], changes[0]['after_sha256'])

    def test_already_canonical_is_unchanged(self):
        original = b'dataset_path: openai/gsm8k\ntask: gsm8k\n'
        self.task.write_bytes(original)
        self.assertEqual(self.repair(), [])
        self.assertEqual(self.task.read_bytes(), original)

    def test_unrelated_repository_and_task_name_are_unchanged(self):
        original = b'dataset_path: example/gsm8k_variant\ntask: gsm8k\n'
        self.task.write_bytes(original)
        self.assertEqual(self.repair(), [])
        self.assertEqual(self.task.read_bytes(), original)

    def test_quoted_name_comment_and_line_endings_preserved(self):
        original = b'dataset_path: "gsm8k"  # official dataset\r\ntask: gsm8k\r\n'
        self.task.write_bytes(original)
        self.repair()
        self.assertEqual(self.task.read_bytes(), original.replace(b'"gsm8k"', b'"openai/gsm8k"'))

    def test_repeat_is_idempotent(self):
        self.task.write_bytes(b'dataset_path: gsm8k\n')
        self.repair()
        first = self.task.read_bytes()
        self.assertEqual(self.repair(), [])
        self.assertEqual(self.task.read_bytes(), first)

    def test_supported_build_includes_repair(self):
        recipe = (ROOT / 'docker/source-current/Dockerfile').read_text()
        # The existing narrow build context is preserved: ship in the sealed archive.
        self.assertIn('COPY dist/source-current/qualify_eval_task_namespaces.py', recipe)
        self.assertIn('/opt/venv/bin/python3 /opt/haloloom/qualify_eval_task_namespaces.py', recipe)


if __name__ == '__main__':
    unittest.main(verbosity=2)
