"""Local JSON-file prompt library.

Stores generated system/user prompt pairs so they can be reused across the
Streamlit app, the REST API service, and the MCP server. The store is a single
JSON file written atomically; every read reloads from disk so the API and MCP
processes stay consistent without a database.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "prompt_library.json"
LIBRARY_SCHEMA_VERSION = "1.0"


def library_path(path: str | os.PathLike | None = None) -> Path:
    """Resolve the library file path (explicit arg > env var > default)."""
    if path is not None:
        return Path(path)
    env_path = os.getenv("PROMPT_LIBRARY_PATH")
    return Path(env_path) if env_path else DEFAULT_LIBRARY_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(system_prompt: str, user_prompt: str) -> str:
    digest = hashlib.sha256()
    digest.update((system_prompt or "").encode("utf-8"))
    digest.update(b"\0")
    digest.update((user_prompt or "").encode("utf-8"))
    return digest.hexdigest()


def _derive_title(persona: str, task: str) -> str:
    parts = [part.strip() for part in (persona, task) if part and part.strip()]
    return " — ".join(parts) if parts else "Untitled prompt"


def _load(path: str | os.PathLike | None = None) -> list[dict]:
    resolved = library_path(path)
    if not resolved.exists():
        return []
    try:
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        data = data.get("prompts", [])
    return [entry for entry in data if isinstance(entry, dict)] if isinstance(data, list) else []


def _atomic_write(prompts: list[dict], path: str | os.PathLike | None = None) -> None:
    resolved = library_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": LIBRARY_SCHEMA_VERSION, "prompts": prompts}
    fd, tmp_name = tempfile.mkstemp(dir=str(resolved.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp_name, resolved)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def save_prompt(
    *,
    system_prompt: str = "",
    user_prompt: str = "",
    title: str = "",
    persona: str = "",
    task: str = "",
    tags: list[str] | None = None,
    approval_status: str = "draft",
    model_name: str = "",
    source_package_id: str = "",
    metadata: dict | None = None,
    dedupe: bool = True,
    path: str | os.PathLike | None = None,
) -> dict:
    """Write a system/user prompt pair to the library and return the stored entry.

    Raises ValueError when both prompts are empty. When ``dedupe`` is True and an
    entry with identical prompt content already exists, that entry is returned
    unchanged instead of creating a duplicate.
    """
    system_prompt = (system_prompt or "").strip()
    user_prompt = (user_prompt or "").strip()
    if not system_prompt and not user_prompt:
        raise ValueError("Cannot save an empty prompt: system_prompt and user_prompt are both empty.")

    prompts = _load(path)
    content_hash = _content_hash(system_prompt, user_prompt)

    if dedupe:
        for entry in prompts:
            if entry.get("content_hash") == content_hash:
                return entry

    combined_tags = list(tags or [])
    for value in (persona, task):
        value = (value or "").strip()
        if value and value not in combined_tags:
            combined_tags.append(value)

    now = _now()
    entry = {
        "id": str(uuid.uuid4()),
        "title": title.strip() or _derive_title(persona, task),
        "persona": persona,
        "task": task,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "tags": combined_tags,
        "approval_status": approval_status,
        "model_name": model_name,
        "source_package_id": source_package_id,
        "content_hash": content_hash,
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
    }
    prompts.append(entry)
    _atomic_write(prompts, path)
    return entry


def save_package_to_library(
    package: dict,
    *,
    tags: list[str] | None = None,
    dedupe: bool = True,
    path: str | os.PathLike | None = None,
) -> dict:
    """Extract the system/user prompt from a generated package and store them."""
    metadata = package.get("metadata", {}) or {}
    return save_prompt(
        system_prompt=package.get("system_prompt", ""),
        user_prompt=package.get("user_prompt_template", ""),
        persona=metadata.get("persona", ""),
        task=metadata.get("task", ""),
        tags=tags,
        approval_status=metadata.get("approval_status", "draft"),
        model_name=metadata.get("model_name", ""),
        source_package_id=metadata.get("prompt_package_id", ""),
        metadata={
            "version_number": metadata.get("version_number"),
            "generator_mode": metadata.get("generator_mode"),
            "prompt_package_version": package.get("prompt_package_version"),
        },
        dedupe=dedupe,
        path=path,
    )


def list_prompts(
    *,
    persona: str | None = None,
    task: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    path: str | os.PathLike | None = None,
) -> list[dict]:
    """Return stored prompts (newest first) matching the optional filters."""
    prompts = _load(path)
    search_term = (search or "").lower().strip()
    results = []
    for entry in prompts:
        if persona and entry.get("persona") != persona:
            continue
        if task and entry.get("task") != task:
            continue
        if tag and tag not in (entry.get("tags") or []):
            continue
        if search_term:
            haystack = " ".join(
                [
                    str(entry.get("title", "")),
                    str(entry.get("persona", "")),
                    str(entry.get("task", "")),
                    str(entry.get("system_prompt", "")),
                    str(entry.get("user_prompt", "")),
                    " ".join(entry.get("tags", []) or []),
                ]
            ).lower()
            if search_term not in haystack:
                continue
        results.append(entry)
    results.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    if limit is not None:
        results = results[: max(0, int(limit))]
    return results


def get_prompt(prompt_id: str, *, path: str | os.PathLike | None = None) -> dict | None:
    """Return a single stored prompt by id, or None if it does not exist."""
    for entry in _load(path):
        if entry.get("id") == prompt_id:
            return entry
    return None


def delete_prompt(prompt_id: str, *, path: str | os.PathLike | None = None) -> bool:
    """Delete a stored prompt by id. Returns True when an entry was removed."""
    prompts = _load(path)
    remaining = [entry for entry in prompts if entry.get("id") != prompt_id]
    if len(remaining) == len(prompts):
        return False
    _atomic_write(remaining, path)
    return True


def count_prompts(*, path: str | os.PathLike | None = None) -> int:
    """Return the number of stored prompts."""
    return len(_load(path))
