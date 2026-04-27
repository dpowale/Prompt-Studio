import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from core.fallback_builder import build_fallback_result
from core.package_service import build_generation_prompt, generate_prompt_package, prepare_metadata


class MockResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class PromptGenerationTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {
            "final_persona": "Marketing Strategist",
            "job_role": "Owns launch messaging and campaign planning.",
            "final_task": "Draft professional emails or letters",
            "additional_context": "Keep the output concise and review-friendly.",
            "style_brief": "Use short paragraphs and clear headings.",
            "factual_brief": "Use only approved product facts.",
            "model_name": "qwen2.5:latest",
            "base_url": "http://localhost:11434",
            "use_quality_helper": False,
            "quality_method": "ChainOfThought",
        }

    def _build_valid_package(self) -> dict:
        metadata = prepare_metadata(
            final_persona=self.inputs["final_persona"],
            final_task=self.inputs["final_task"],
            model_name=self.inputs["model_name"],
            base_url=self.inputs["base_url"],
            generator_mode="standard",
            style_sources=[],
            factual_sources=[],
            quality_helper_enabled=False,
            quality_method=self.inputs["quality_method"],
        )
        return build_fallback_result(
            self.inputs["final_persona"],
            self.inputs["job_role"],
            self.inputs["final_task"],
            self.inputs["additional_context"],
            style_brief=self.inputs["style_brief"],
            factual_brief=self.inputs["factual_brief"],
            metadata=metadata,
        )

    def test_generation_prompt_mentions_schema_and_grounding(self):
        template_package = self._build_valid_package()
        prompt = build_generation_prompt(
            template_package,
            self.inputs["final_persona"],
            self.inputs["job_role"],
            self.inputs["final_task"],
            self.inputs["additional_context"],
            self.inputs["style_brief"],
            self.inputs["factual_brief"],
        )

        self.assertIn("Return one JSON object only", prompt)
        self.assertIn("Style grounding brief", prompt)
        self.assertIn("Factual grounding brief", prompt)
        self.assertIn("[SOURCE_ID]", prompt)
        self.assertIn("user_prompt_template", prompt)

    @patch("core.package_service.requests.post")
    def test_generate_prompt_package_returns_valid_package(self, mock_post):
        valid_package = self._build_valid_package()
        valid_package["system_prompt"] = valid_package["system_prompt"] + " Extra reviewer note for testing."
        mock_post.return_value = MockResponse({"response": json.dumps(valid_package)})

        package, errors = generate_prompt_package(**self.inputs)

        self.assertEqual(errors, [])
        self.assertEqual(package["metadata"]["generator_mode"], "standard")
        self.assertIn("evaluation", package)
        self.assertEqual(package["metadata"]["model_name"], self.inputs["model_name"])
        self.assertTrue(package["system_prompt"].startswith("You are"))
        mock_post.assert_called_once()

    @patch("core.package_service.requests.post")
    def test_generate_prompt_package_repairs_partial_model_output(self, mock_post):
        partial_package = {
            "system_prompt": (
                "You are a marketing strategist who must produce compliant output using approved sources only. "
                "Always separate facts from assumptions, flag uncertainty, avoid invented claims, and recommend human review when needed."
            ),
            "user_prompt_template": (
                "Use [TASK_GOAL], [INPUT_CONTENT], [CONSTRAINTS], [OUTPUT_AUDIENCE], and [DELIVERABLE_FORMAT]. "
                "Provide: (1) draft copy, (2) risks, (3) source notes."
            ),
        }
        mock_post.return_value = MockResponse({"response": json.dumps(partial_package)})

        package, errors = generate_prompt_package(**self.inputs)

        self.assertEqual(errors, [])
        self.assertEqual(package["metadata"]["generator_mode"], "standard (repaired)")
        self.assertIn("repair_notes", package["metadata"])
        self.assertIn("acceptance_tests", package)
        self.assertIn("evaluation", package)
        mock_post.assert_called_once()

    @patch("core.package_service.requests.post")
    def test_generate_prompt_package_falls_back_after_runtime_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("network down")

        package, errors = generate_prompt_package(**self.inputs)

        self.assertEqual(errors, ["network down"])
        self.assertEqual(package["metadata"]["generator_mode"], "fallback after runtime issue")
        self.assertEqual(package["metadata"]["validation_errors"], ["network down"])
        self.assertIn("evaluation", package)


if __name__ == "__main__":
    unittest.main()
