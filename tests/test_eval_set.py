import ast
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EVAL_SET_PATH = PROJECT_ROOT / "evals" / "prompt_package_eval_set.json"
PROMPT_STUDIO_PATH = PROJECT_ROOT / "prompt_studio.py"


def _load_prompt_studio_constants() -> tuple[set[str], set[str]]:
    tree = ast.parse(PROMPT_STUDIO_PATH.read_text(encoding="utf-8"))
    personas: set[str] = set()
    tasks: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PERSONAS":
                    personas_dict = ast.literal_eval(node.value)
                    personas = {value[0] for value in personas_dict.values()}
                if isinstance(target, ast.Name) and target.id == "TASKS":
                    tasks = set(ast.literal_eval(node.value))
    return personas, tasks


class EvalSetCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
        cls.persona_ids, cls.tasks = _load_prompt_studio_constants()

    def test_eval_set_has_required_top_level_keys(self):
        self.assertIn("coverage_summary", self.eval_set)
        self.assertIn("default_expectations", self.eval_set)
        self.assertIn("scenarios", self.eval_set)
        self.assertTrue(self.eval_set["scenarios"])

    def test_eval_set_covers_all_personas(self):
        scenario_personas = {scenario["persona_id"] for scenario in self.eval_set["scenarios"]}
        self.assertEqual(scenario_personas, self.persona_ids)

    def test_eval_set_covers_all_tasks(self):
        scenario_tasks = {scenario["task"] for scenario in self.eval_set["scenarios"]}
        self.assertEqual(scenario_tasks, self.tasks)

    def test_eval_set_covers_grounding_modes_and_document_types(self):
        grounding_modes = {scenario["grounding_mode"] for scenario in self.eval_set["scenarios"]}
        self.assertEqual(grounding_modes, set(self.eval_set["coverage_summary"]["grounding_modes"]))

        document_types = set()
        for scenario in self.eval_set["scenarios"]:
            for source in scenario.get("style_sources", []) + scenario.get("factual_sources", []):
                document_types.add(source["document_type"])
        self.assertEqual(document_types, set(self.eval_set["coverage_summary"]["document_types"]))

    def test_eval_set_covers_generation_styles(self):
        styles = {scenario["generation_style"] for scenario in self.eval_set["scenarios"]}
        self.assertEqual(styles, set(self.eval_set["coverage_summary"]["generation_styles"]))

    def test_each_scenario_has_core_fields(self):
        required_fields = {
            "id",
            "title",
            "persona_id",
            "task",
            "job_role",
            "additional_context",
            "grounding_mode",
            "generation_style",
            "style_sources",
            "factual_sources",
            "coverage_tags",
        }
        for scenario in self.eval_set["scenarios"]:
            self.assertTrue(required_fields.issubset(set(scenario.keys())), msg=f"Missing required fields in {scenario.get('id')}")
            self.assertIsInstance(scenario["style_sources"], list)
            self.assertIsInstance(scenario["factual_sources"], list)
            self.assertIsInstance(scenario["coverage_tags"], list)


if __name__ == "__main__":
    unittest.main()
