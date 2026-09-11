"""CPU orchestration checks; the separate image tests verify real native loading."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('quark_rebuild_inputs', ROOT / 'scripts/build_release_inputs.py')
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class QuarkNativeRebuild(unittest.TestCase):
    def test_documented_shell_requests_native_packaging(self):
        text = (ROOT / 'scripts/build_images.sh').read_text()
        self.assertIn('set -- "$@" --package-quark-native', text)
        self.assertIn('exec python3 "$ROOT/scripts/build_release_inputs.py" "$@"', text)

    def test_native_packaging_uses_real_recipe_offline_and_same_output(self):
        self.assertTrue(hasattr(BUILDER, 'package_quark_native'))
        with patch.object(BUILDER.subprocess, 'run') as run:
            BUILDER.package_quark_native(root=ROOT, tag='haloloom-candidate:quark-test')
        run.assert_called_once_with([
            'docker', 'build', '--network', 'none', '--build-arg',
            'BASE_IMAGE=haloloom-candidate:quark-test', '-f',
            'docker/quark-native-extension/Dockerfile', '-t',
            'haloloom-candidate:quark-test', '.',
        ], cwd=ROOT, check=True)

    def test_native_layer_runs_after_source_inputs(self):
        phases = []
        with patch.object(BUILDER, 'prepare', side_effect=lambda *a, **kw: phases.append('inputs')):
            with patch.object(BUILDER.subprocess, 'run', side_effect=lambda *a, **kw: phases.append('native')):
                self.assertEqual(BUILDER.main(['--package-quark-native']), 0)
        self.assertEqual(phases, ['inputs', 'native'])

    def test_failed_source_inputs_do_not_package(self):
        with patch.object(BUILDER, 'prepare', side_effect=BUILDER.InputError('fixture: source failure')):
            with patch.object(BUILDER.subprocess, 'run') as run:
                self.assertEqual(BUILDER.main(['--package-quark-native']), 1)
                run.assert_not_called()

    def test_failed_native_layer_is_not_a_successful_build(self):
        with patch.object(BUILDER, 'prepare'):
            with patch.object(BUILDER.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['docker', 'build'])):
                self.assertEqual(BUILDER.main(['--package-quark-native']), 1)

    def test_input_only_api_remains_available(self):
        with patch.object(BUILDER, 'prepare'):
            with patch.object(BUILDER.subprocess, 'run') as run:
                self.assertEqual(BUILDER.main([]), 0)
                run.assert_not_called()
