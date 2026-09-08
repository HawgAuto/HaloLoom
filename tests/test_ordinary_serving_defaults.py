"""Additional default-routing regressions; existing tests are unchanged."""
import importlib.util
from pathlib import Path

import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class OrdinaryServingDefaultsTests(unittest.TestCase):
    def test_image_defaults_disable_optional_bridge(self):
        dockerfile = (ROOT / "docker/source-current/Dockerfile").read_text()
        self.assertRegex(dockerfile, r"HYPERLOOM_GFX1151_LOWBIT_BRIDGE=0(?:\s|$)")

    def test_all_native_workbenches_default_to_ordinary_serving(self):
        services = yaml.safe_load((ROOT / "compose.yaml").read_text())["services"]
        for service in ("vllm", "sglang", "quark"):
            with self.subTest(service=service):
                self.assertEqual(services[service]["environment"].get("HYPERLOOM_GFX1151_LOWBIT_BRIDGE"), "0")

    def serving_helper(self):
        spec = importlib.util.spec_from_file_location("ordinary_serve", ROOT / "scripts/serve.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_bf16_and_native_quark_do_not_opt_into_custom_routes(self):
        for extra in ([], ["--quantization", "quark"]):
            with self.subTest(extra=extra):
                command = self.serving_helper().build_command("vllm", "/models/local", extra, max_model_len=2048)
                self.assertNotIn("HYPERLOOM_GFX1151_LOWBIT_BRIDGE=1", command)

    def test_optional_custom_routes_still_require_revision(self):
        with self.assertRaisesRegex(ValueError, "model revision"):
            self.serving_helper().build_command("vllm", "/models/local", ["--quantization", "gfx1151-w4a4"], max_model_len=2048)


if __name__ == "__main__":
    unittest.main(verbosity=2)
