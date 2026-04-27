import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.run_eval_set import evaluate_scenario_result, run_eval_set, scenario_to_request_payload


class EvalRunnerTests(unittest.TestCase):
    def setUp(self):
        self.scenario = {
            "id": "EVAL-TEST",
            "title": "Test scenario",
            "persona_id": "marketer",
            "task": "Draft professional emails or letters",
            "job_role": "Owns messaging and reviews launch copy.",
            "additional_context": "Keep it concise.",
            "grounding_mode": "style_and_factual",
            "generation_style": "quality_helper_highest",
            "style_sources": [
                {
                    "name": "brand.docx",
                    "document_type": "docx",
                    "content_excerpt": "Friendly but precise tone.",
                    "purpose": "Brand voice",
                }
            ],
            "factual_sources": [
                {
                    "name": "facts.txt",
                    "document_type": "txt",
                    "content_excerpt": "Approved launch date and feature list.",
                    "purpose": "Approved facts",
                }
            ],
            "coverage_tags": ["docx", "txt"],
        }
        self.defaults = {
            "min_score_pct": 100,
            "required_checks": ["System prompt opens with 'You are'"],
            "expected_status": "draft",
            "required_placeholders": ["TASK_GOAL", "INPUT_CONTENT"],
        }

    def test_scenario_to_request_payload_maps_generation_style_and_sources(self):
        payload = scenario_to_request_payload(
            self.scenario,
            model_name="qwen2.5:latest",
            base_url="http://localhost:11434",
            version_number=3,
            approval_status="draft",
        )

        self.assertEqual(payload["final_persona"], "Marketing Strategist")
        self.assertTrue(payload["use_quality_helper"])
        self.assertEqual(payload["quality_method"], "BestOfN")
        self.assertEqual(payload["style_sources"][0]["source_id"], "SOURCE_STYLE_1")
        self.assertIn("Brand voice", payload["style_brief"])
        self.assertIn("Approved facts", payload["factual_brief"])

    def test_evaluate_scenario_result_passes_for_compliant_package(self):
        package = {
            "user_prompt_template": "Use [TASK_GOAL] and [INPUT_CONTENT]. Provide: (1) summary.",
            "metadata": {"approval_status": "draft", "generator_mode": "standard", "prompt_package_id": "pkg-1"},
            "evaluation": {
                "score_pct": 100,
                "checks": [{"label": "System prompt opens with 'You are'", "passed": True}],
            },
        }

        result = evaluate_scenario_result(self.scenario, package, [], self.defaults)

        self.assertTrue(result["passed"])
        self.assertEqual(result["missing_required_checks"], [])
        self.assertEqual(result["missing_placeholders"], [])

    @patch("evals.run_eval_set.generate_prompt_package")
    def test_run_eval_set_writes_json_csv_and_markdown_reports(self, mock_generate):
        mock_generate.return_value = (
            {
                "user_prompt_template": "Use [TASK_GOAL] and [INPUT_CONTENT]. Provide: (1) summary.",
                "metadata": {"approval_status": "draft", "generator_mode": "standard", "prompt_package_id": "pkg-1"},
                "evaluation": {
                    "score_pct": 100,
                    "checks": [{"label": "System prompt opens with 'You are'", "passed": True}],
                },
            },
            [],
        )

        eval_set = {
            "title": "Mini eval set",
            "default_expectations": self.defaults,
            "scenarios": [self.scenario],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            eval_path = Path(temp_dir) / "eval_set.json"
            output_dir = Path(temp_dir) / "results"
            eval_path.write_text(json.dumps(eval_set), encoding="utf-8")

            report = run_eval_set(
                eval_set_path=eval_path,
                model_name="qwen2.5:latest",
                base_url="http://localhost:11434",
                output_dir=output_dir,
            )

            self.assertEqual(report["passed_count"], 1)
            self.assertEqual(report["total_count"], 1)
            output_files = report["output_files"]
            self.assertTrue(Path(output_files["json"]).exists())
            self.assertTrue(Path(output_files["csv"]).exists())
            self.assertTrue(Path(output_files["markdown"]).exists())


if __name__ == "__main__":
    unittest.main()
