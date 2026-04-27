from __future__ import annotations

import importlib
from typing import Any

FastAPI = importlib.import_module("fastapi").FastAPI
pydantic = importlib.import_module("pydantic")
BaseModel = pydantic.BaseModel
Field = pydantic.Field

from core.package_service import DSPY_AVAILABLE, dspy_helper_ready, generate_prompt_package


class SourceDocument(BaseModel):
    source_id: str | None = None
    name: str | None = None
    summary: str | None = None
    text: str | None = None
    error: str | None = None


class GeneratePackageRequest(BaseModel):
    persona: str = Field(..., description="Professional persona name")
    job_role: str = Field(..., description="Role responsibilities and scope")
    task: str = Field(..., description="The task to perform")
    additional_context: str = ""
    style_brief: str = ""
    factual_brief: str = ""
    style_sources: list[SourceDocument] = Field(default_factory=list)
    factual_sources: list[SourceDocument] = Field(default_factory=list)
    model_name: str = "llama3.1:latest"
    base_url: str = "http://localhost:11434"
    use_quality_helper: bool = False
    quality_method: str = "ChainOfThought"
    version_number: int = 1
    approval_status: str = "draft"


app = FastAPI(title="Prompt Studio API", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "quality_helper_available": DSPY_AVAILABLE,
        "quality_helper_ready": dspy_helper_ready(),
    }


@app.post("/generate-package")
def generate_package(request: GeneratePackageRequest) -> dict[str, Any]:
    package, validation_errors = generate_prompt_package(
        final_persona=request.persona,
        job_role=request.job_role,
        final_task=request.task,
        additional_context=request.additional_context,
        style_brief=request.style_brief,
        factual_brief=request.factual_brief,
        style_sources=[item.model_dump() for item in request.style_sources],
        factual_sources=[item.model_dump() for item in request.factual_sources],
        model_name=request.model_name,
        base_url=request.base_url,
        use_quality_helper=request.use_quality_helper,
        quality_method=request.quality_method,
        version_number=request.version_number,
        approval_status=request.approval_status,
    )
    return {
        "package": package,
        "validation_errors": validation_errors,
    }
