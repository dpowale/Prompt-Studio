"""Prompt Studio prompt-library MCP server (stdio transport).

Exposes the local JSON prompt library (core/prompt_library.py) to MCP clients
such as Claude Desktop. The same store backs the REST API in api_server.py.

Run it directly:

    python mcp_server.py

Or register it with an MCP client using the command above. Set the
PROMPT_LIBRARY_PATH environment variable to point at a specific library file.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from core import prompt_library

mcp = FastMCP("prompt-studio-library")


@mcp.tool()
def save_prompt(
    system_prompt: str = "",
    user_prompt: str = "",
    title: str = "",
    persona: str = "",
    task: str = "",
    tags: list[str] | None = None,
    approval_status: str = "draft",
    model_name: str = "",
    source_package_id: str = "",
    dedupe: bool = True,
) -> dict:
    """Save a system/user prompt pair to the Prompt Studio library.

    Returns the stored entry (including its generated id). At least one of
    system_prompt or user_prompt must be non-empty.
    """
    return prompt_library.save_prompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        title=title,
        persona=persona,
        task=task,
        tags=tags,
        approval_status=approval_status,
        model_name=model_name,
        source_package_id=source_package_id,
        dedupe=dedupe,
    )


@mcp.tool()
def list_prompts(
    persona: str = "",
    task: str = "",
    tag: str = "",
    search: str = "",
    limit: int = 0,
) -> list[dict]:
    """List saved prompts (newest first), optionally filtered.

    Empty string filters and limit=0 mean "no filter".
    """
    return prompt_library.list_prompts(
        persona=persona or None,
        task=task or None,
        tag=tag or None,
        search=search or None,
        limit=limit or None,
    )


@mcp.tool()
def get_prompt(prompt_id: str) -> dict | None:
    """Fetch a single saved prompt by id. Returns null if it does not exist."""
    return prompt_library.get_prompt(prompt_id)


@mcp.tool()
def delete_prompt(prompt_id: str) -> dict:
    """Delete a saved prompt by id. Returns whether an entry was removed."""
    return {"deleted": prompt_library.delete_prompt(prompt_id), "id": prompt_id}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
