import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.llm_api import call_external_llm_api, fetch_external_models


class MockResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class ExternalLlmApiTests(unittest.TestCase):
    @patch("core.llm_api.requests.post")
    def test_call_external_llm_api_openai_compatible(self, mock_post):
        mock_post.return_value = MockResponse(
            {"choices": [{"message": {"content": "Generated text from compatible API"}}]}
        )

        result = call_external_llm_api(
            provider="openai-compatible",
            base_url="https://example.com/v1",
            model_name="gpt-test",
            prompt="Write a short reply",
            api_key="secret",
            system_prompt="Be concise.",
        )

        self.assertEqual(result, "Generated text from compatible API")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["messages"][0]["role"], "system")
        self.assertEqual(kwargs["json"]["messages"][1]["role"], "user")

    @patch("core.llm_api.requests.post")
    def test_call_external_llm_api_anthropic(self, mock_post):
        mock_post.return_value = MockResponse(
            {"content": [{"type": "text", "text": "Anthropic-style response"}]}
        )

        result = call_external_llm_api(
            provider="anthropic",
            base_url="https://example.com/v1",
            model_name="claude-test",
            prompt="Summarize this",
            api_key="secret",
            system_prompt="Be careful.",
        )

        self.assertEqual(result, "Anthropic-style response")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["x-api-key"], "secret")
        self.assertEqual(kwargs["json"]["system"], "Be careful.")

    @patch("core.llm_api.requests.get")
    def test_fetch_external_models_returns_sorted_model_ids(self, mock_get):
        mock_get.return_value = MockResponse(
            {"data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "a-model"}]}
        )

        models = fetch_external_models(
            provider="openai-compatible",
            base_url="https://example.com/v1",
            api_key="secret",
        )

        self.assertEqual(models, ["a-model", "z-model"])


if __name__ == "__main__":
    unittest.main()
