from __future__ import annotations

import importlib
from typing import Any

_fastapi = importlib.import_module("fastapi")
FastAPI = _fastapi.FastAPI
HTTPException = _fastapi.HTTPException
pydantic = importlib.import_module("pydantic")
BaseModel = pydantic.BaseModel
Field = pydantic.Field

from core import prompt_library


class SavePromptRequest(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""
    title: str = ""
    persona: str = ""
    task: str = ""
    tags: list[str] = Field(default_factory=list)
    approval_status: str = "draft"
    model_name: str = ""
    source_package_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    dedupe: bool = True


class SavePackageRequest(BaseModel):
    package: dict[str, Any] = Field(..., description="A generated prompt package")
    tags: list[str] = Field(default_factory=list)
    dedupe: bool = True


app = FastAPI(title="Prompt Studio Library API", version="2.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "library_path": str(prompt_library.library_path()),
        "library_count": prompt_library.count_prompts(),
    }


@app.post("/library/prompts")
def library_save_prompt(request: SavePromptRequest) -> dict[str, Any]:
    try:
        entry = prompt_library.save_prompt(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            title=request.title,
            persona=request.persona,
            task=request.task,
            tags=request.tags,
            approval_status=request.approval_status,
            model_name=request.model_name,
            source_package_id=request.source_package_id,
            metadata=request.metadata,
            dedupe=request.dedupe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"prompt": entry}


@app.post("/library/save-package")
def library_save_package(request: SavePackageRequest) -> dict[str, Any]:
    try:
        entry = prompt_library.save_package_to_library(
            request.package,
            tags=request.tags,
            dedupe=request.dedupe,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"prompt": entry}


@app.get("/library/prompts")
def library_list_prompts(
    persona: str | None = None,
    task: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    prompts = prompt_library.list_prompts(
        persona=persona,
        task=task,
        tag=tag,
        search=search,
        limit=limit,
    )
    return {"prompts": prompts, "count": len(prompts)}


@app.get("/library/prompts/{prompt_id}")
def library_get_prompt(prompt_id: str) -> dict[str, Any]:
    entry = prompt_library.get_prompt(prompt_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"prompt": entry}


@app.delete("/library/prompts/{prompt_id}")
def library_delete_prompt(prompt_id: str) -> dict[str, Any]:
    if not prompt_library.delete_prompt(prompt_id):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"deleted": True, "id": prompt_id}
