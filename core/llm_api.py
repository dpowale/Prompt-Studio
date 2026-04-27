from __future__ import annotations

from typing import Any

import requests

def fetch_ollama_models(base_url: str):
    """Return a sorted list of model names from a local Ollama instance."""
    try:
        response = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=10)
        response.raise_for_status()
        payload = response.json()
        models = [item.get("name", "").strip() for item in payload.get("models", []) if item.get("name")]
        return sorted(dict.fromkeys(models), key=str.lower)
    except Exception:
        return []


def call_external_llm_api(
    *,
    provider: str,
    base_url: str,
    model_name: str,
    prompt: str,
    api_key: str | None = None,
    system_prompt: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 3000,
    timeout: int = 90,
    extra_headers: dict[str, str] | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> str:
    """Call an external LLM API and return the generated text.

    Supported providers:
    - ``openai-compatible``: any endpoint exposing ``/chat/completions``
    - ``anthropic``: Anthropic-compatible ``/messages`` endpoint
    """
    provider_name = (provider or "openai-compatible").strip().lower()
    root_url = base_url.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)

    if provider_name in {"openai", "openai-compatible"}:
        if api_key:
            headers.setdefault("Authorization", f"Bearer {api_key}")
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if system_prompt:
            payload["messages"].append({"role": "system", "content": system_prompt})
        payload["messages"].append({"role": "user", "content": prompt})
        if extra_payload:
            payload.update(extra_payload)

        response = requests.post(f"{root_url}/chat/completions", headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        response_payload = response.json()
        choices = response_payload.get("choices") or []
        if not choices:
            raise ValueError("External API returned no choices.")
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            return "\n".join(str(item.get("text", "")).strip() for item in content if isinstance(item, dict) and item.get("text")).strip()
        return str(content).strip()

    if provider_name == "anthropic":
        if not api_key:
            raise ValueError("Anthropic-compatible requests require an API key.")
        headers.setdefault("x-api-key", api_key)
        headers.setdefault("anthropic-version", "2023-06-01")
        payload = {
            "model": model_name,
            "system": system_prompt or "",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if extra_payload:
            payload.update(extra_payload)

        response = requests.post(f"{root_url}/messages", headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        response_payload = response.json()
        content_blocks = response_payload.get("content") or []
        text_parts = [block.get("text", "").strip() for block in content_blocks if isinstance(block, dict) and block.get("type") == "text"]
        if not text_parts:
            raise ValueError("External API returned no text content.")
        return "\n".join(part for part in text_parts if part).strip()

    raise ValueError(f"Unsupported external provider: {provider}")


def fetch_external_models(
    *,
    provider: str,
    base_url: str,
    api_key: str | None = None,
    timeout: int = 15,
    extra_headers: dict[str, str] | None = None,
) -> list[str]:
    """Return a sorted list of models from an external provider when supported."""
    provider_name = (provider or "openai-compatible").strip().lower()
    headers = extra_headers.copy() if extra_headers else {}

    if provider_name in {"openai", "openai-compatible"} and api_key:
        headers.setdefault("Authorization", f"Bearer {api_key}")
    elif provider_name == "anthropic":
        if not api_key:
            return []
        headers.setdefault("x-api-key", api_key)
        headers.setdefault("anthropic-version", "2023-06-01")

    try:
        response = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        models = [item.get("id", "").strip() for item in payload.get("data", []) if item.get("id")]
        return sorted(dict.fromkeys(models), key=str.lower)
    except Exception:
        return []
