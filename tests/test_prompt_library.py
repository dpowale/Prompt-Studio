import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import prompt_library


class PromptLibraryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.lib_path = Path(self._tmp.name) / "library.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_prompt_creates_entry_with_identifiers(self):
        entry = prompt_library.save_prompt(
            system_prompt="You are an expert analyst.",
            user_prompt="Summarize [INPUT_CONTENT]. Provide: (1) summary.",
            persona="Financial Analyst",
            task="Summarize a document",
            tags=["finance"],
            path=self.lib_path,
        )

        self.assertTrue(entry["id"])
        self.assertEqual(entry["title"], "Financial Analyst — Summarize a document")
        self.assertEqual(entry["persona"], "Financial Analyst")
        self.assertEqual(entry["tags"], ["finance", "Financial Analyst", "Summarize a document"])
        self.assertIn("content_hash", entry)
        self.assertEqual(entry["created_at"], entry["updated_at"])
        self.assertEqual(prompt_library.count_prompts(path=self.lib_path), 1)

    def test_save_prompt_rejects_empty_content(self):
        with self.assertRaises(ValueError):
            prompt_library.save_prompt(system_prompt="  ", user_prompt="", path=self.lib_path)

    def test_dedupe_returns_existing_entry_for_identical_content(self):
        first = prompt_library.save_prompt(system_prompt="You are X.", user_prompt="Do Y.", path=self.lib_path)
        second = prompt_library.save_prompt(system_prompt="You are X.", user_prompt="Do Y.", path=self.lib_path)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(prompt_library.count_prompts(path=self.lib_path), 1)

    def test_dedupe_disabled_creates_separate_entries(self):
        first = prompt_library.save_prompt(system_prompt="You are X.", user_prompt="Do Y.", path=self.lib_path)
        second = prompt_library.save_prompt(system_prompt="You are X.", user_prompt="Do Y.", dedupe=False, path=self.lib_path)

        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(prompt_library.count_prompts(path=self.lib_path), 2)

    def test_list_prompts_filters_and_orders_newest_first(self):
        older = prompt_library.save_prompt(system_prompt="You are A.", user_prompt="A.", persona="HR Professional", task="Policy", path=self.lib_path)
        newer = prompt_library.save_prompt(system_prompt="You are B.", user_prompt="B.", persona="Researcher", task="Study", tags=["lit"], path=self.lib_path)

        all_prompts = prompt_library.list_prompts(path=self.lib_path)
        self.assertEqual([p["id"] for p in all_prompts][0], newer["id"])

        by_persona = prompt_library.list_prompts(persona="HR Professional", path=self.lib_path)
        self.assertEqual([p["id"] for p in by_persona], [older["id"]])

        by_tag = prompt_library.list_prompts(tag="lit", path=self.lib_path)
        self.assertEqual([p["id"] for p in by_tag], [newer["id"]])

        by_search = prompt_library.list_prompts(search="study", path=self.lib_path)
        self.assertEqual([p["id"] for p in by_search], [newer["id"]])

    def test_get_and_delete_prompt(self):
        entry = prompt_library.save_prompt(system_prompt="You are X.", user_prompt="Do Y.", path=self.lib_path)

        self.assertEqual(prompt_library.get_prompt(entry["id"], path=self.lib_path)["id"], entry["id"])
        self.assertIsNone(prompt_library.get_prompt("missing-id", path=self.lib_path))

        self.assertTrue(prompt_library.delete_prompt(entry["id"], path=self.lib_path))
        self.assertFalse(prompt_library.delete_prompt(entry["id"], path=self.lib_path))
        self.assertEqual(prompt_library.count_prompts(path=self.lib_path), 0)

    def test_save_package_to_library_extracts_prompt_fields(self):
        package = {
            "prompt_package_version": "2.0",
            "system_prompt": "You are a marketing strategist.",
            "user_prompt_template": "Use [TASK_GOAL]. Provide: (1) draft.",
            "metadata": {
                "persona": "Marketing Strategist",
                "task": "Draft an email",
                "approval_status": "approved",
                "model_name": "qwen2.5:latest",
                "prompt_package_id": "pkg-123",
                "version_number": 2,
                "generator_mode": "standard",
            },
        }

        entry = prompt_library.save_package_to_library(package, tags=["launch"], path=self.lib_path)

        self.assertEqual(entry["system_prompt"], package["system_prompt"])
        self.assertEqual(entry["user_prompt"], package["user_prompt_template"])
        self.assertEqual(entry["persona"], "Marketing Strategist")
        self.assertEqual(entry["approval_status"], "approved")
        self.assertEqual(entry["source_package_id"], "pkg-123")
        self.assertEqual(entry["tags"], ["launch", "Marketing Strategist", "Draft an email"])
        self.assertEqual(entry["metadata"]["version_number"], 2)
        self.assertEqual(entry["metadata"]["prompt_package_version"], "2.0")

    def test_persona_and_task_added_as_tags_without_duplicates(self):
        entry = prompt_library.save_prompt(
            system_prompt="You are X.",
            user_prompt="Do Y.",
            persona="Researcher",
            task="Study",
            tags=["Researcher", "custom"],
            path=self.lib_path,
        )

        # "Researcher" already present is not duplicated; "Study" (task) is appended.
        self.assertEqual(entry["tags"], ["Researcher", "custom", "Study"])

    def test_persona_task_filters_match_auto_added_tags(self):
        entry = prompt_library.save_prompt(
            system_prompt="You are X.",
            user_prompt="Do Y.",
            persona="HR Professional",
            task="Policy review",
            path=self.lib_path,
        )

        self.assertEqual(entry["tags"], ["HR Professional", "Policy review"])
        by_persona_tag = prompt_library.list_prompts(tag="HR Professional", path=self.lib_path)
        by_task_tag = prompt_library.list_prompts(tag="Policy review", path=self.lib_path)
        self.assertEqual([p["id"] for p in by_persona_tag], [entry["id"]])
        self.assertEqual([p["id"] for p in by_task_tag], [entry["id"]])


if __name__ == "__main__":
    unittest.main()
