import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import dspy_module


@unittest.skipUnless(dspy_module.DSPY_AVAILABLE, "DSPy not installed")
class DSPyModuleTests(unittest.TestCase):
    def test_prompt_quality_metric_returns_float_between_zero_and_one(self):
        pred = SimpleNamespace(
            system_prompt="You are a marketing strategist who must escalate unsupported claims and never fabricate evidence.",
            user_prompt="Use [TASK_GOAL] and [INPUT_CONTENT]. Provide: (1) draft, (2) risks.",
            persona_analysis="This professional reasons carefully about evidence and audience while keeping messaging grounded and compliant.",
        )

        score = dspy_module.prompt_quality_metric(SimpleNamespace(), pred)

        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        self.assertGreater(score, 0.0)

    def test_prompt_quality_metric_scores_empty_prediction_zero(self):
        pred = SimpleNamespace(system_prompt="", user_prompt="", persona_analysis="")

        self.assertEqual(dspy_module.prompt_quality_metric(SimpleNamespace(), pred), 0.0)

    @patch("core.dspy_module.dspy.BootstrapFewShot")
    @patch("core.dspy_module.dspy.context")
    def test_compile_dspy_module_uses_bootstrap_and_saves(self, mock_context, mock_bootstrap):
        mock_context.return_value.__enter__.return_value = None
        mock_context.return_value.__exit__.return_value = False
        compiled_module = MagicMock()
        mock_bootstrap.return_value.compile.return_value = compiled_module

        result = dspy_module.compile_dspy_module(lm=object(), trainset=["seed-example"])

        self.assertIs(result, compiled_module)
        mock_bootstrap.assert_called_once()
        compile_kwargs = mock_bootstrap.return_value.compile.call_args.kwargs
        self.assertEqual(compile_kwargs["trainset"], ["seed-example"])
        compiled_module.save.assert_called_once_with(dspy_module.COMPILED_MODULE_PATH)

    @patch("core.dspy_module.os.path.exists")
    def test_load_or_build_module_loads_when_compiled_artifact_exists(self, mock_exists):
        mock_exists.return_value = True

        with patch.object(dspy_module, "PromptEngineerModule") as mock_module_cls:
            instance = mock_module_cls.return_value
            module, status = dspy_module._load_or_build_module()

        self.assertIs(module, instance)
        self.assertEqual(status, "loaded")
        instance.load.assert_called_once_with(dspy_module.COMPILED_MODULE_PATH)

    @patch("core.dspy_module.os.path.exists")
    def test_load_or_build_module_falls_back_when_artifact_missing(self, mock_exists):
        mock_exists.return_value = False

        with patch.object(dspy_module, "PromptEngineerModule") as mock_module_cls:
            instance = mock_module_cls.return_value
            module, status = dspy_module._load_or_build_module()

        self.assertIs(module, instance)
        self.assertEqual(status, "uncompiled")
        instance.load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
