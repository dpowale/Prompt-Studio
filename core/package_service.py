from __future__ import annotations

import copy
import importlib
import json
import os
import uuid
from datetime import datetime, timezone

import requests

from core.fallback_builder import PROMPT_PACKAGE_VERSION, build_fallback_result
from core.utils import extract_prompt_package, finalize_prompt_package, merge_prompt_package, validate_prompt_package

try:
    dspy = importlib.import_module("dspy")
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

if DSPY_AVAILABLE:
    from core.dspy_module import COMPILED_MODULE_PATH, BestOfNModule, _load_or_build_module, compile_dspy_module
else:
    COMPILED_MODULE_PATH = ""


def build_generation_prompt(template_package: dict, final_persona: str, job_role: str, final_task: str, additional_context: str, style_brief: str, factual_brief: str) -> str:
    return f"""
Return one JSON object only. Do not use markdown fences. The object must validate exactly against the structure and data types shown in the schema example below.

Schema example:
{json.dumps(template_package, indent=2)}

Now generate a new structured prompt package for these inputs:
- Persona: {final_persona}
- Role scope: {job_role}
- Task: {final_task}
- Additional constraints: {additional_context or 'None provided'}
- Style grounding brief: {style_brief or 'None provided'}
- Factual grounding brief: {factual_brief or 'None provided'}

Requirements:
1. `system_prompt` must start with "You are" and concisely set role scope, accepted data sources, grounding rules, uncertainty handling, and the key refusal/escalation triggers — only what changes the model's behavior.
2. `user_prompt_template` must include semantically named placeholders such as [TASK_GOAL], [INPUT_CONTENT], [CONSTRAINTS], [OUTPUT_AUDIENCE], [DELIVERABLE_FORMAT], [STYLE_GUIDE], [FACTUAL_SOURCES], and [FACT_SOURCE_1] where relevant.
3. When factual grounding is present, require inline source attribution using [SOURCE_ID] tokens and separate verified facts from assumptions.
4. Keep `input_schema`, `output_schema`, `safety_policy`, `escalation_policy`, `acceptance_tests`, and `metadata` as JSON objects or arrays, not strings.
5. Never fabricate citations, policies, legal conclusions, medical advice, financial claims, or customer-specific facts.
6. Be concise and specific: plain language, no filler, hedging, or repetition. Aim for roughly 90–150 words in `system_prompt` and 60–120 in `user_prompt_template`, and keep the package auditable by a human reviewer.
""".strip()


def build_repair_prompt(candidate_package: dict, template_package: dict, validation_errors: list[str]) -> str:
    return f"""
Repair the JSON object below so it exactly matches the schema and field shapes of the template package. Return one JSON object only. Do not use markdown fences.

Template package:
{json.dumps(template_package, indent=2)}

Candidate package to repair:
{json.dumps(candidate_package, indent=2)}

Validation errors to fix:
{json.dumps(validation_errors, indent=2)}

Repair rules:
1. Preserve the candidate's useful wording when it already meets the template's structural rules.
2. Add any missing fields from the template package.
3. Keep `input_schema`, `output_schema`, `safety_policy`, `escalation_policy`, `acceptance_tests`, and `metadata` as JSON objects or arrays, never as strings.
4. Ensure `user_prompt_template` contains at least 5 semantically named placeholders and an inline output contract beginning with `Provide:` or `(1)`.
5. Ensure `system_prompt` starts with `You are`, stays at least 80 words, and is concise (no filler or repetition).
6. Ensure all factual-grounding rules use `[SOURCE_ID]` notation.
""".strip()


def format_generation_style(use_quality_helper: bool) -> str:
    return "quality helper" if use_quality_helper else "standard"


def format_quality_mode(method: str) -> str:
    return "balanced" if method == "ChainOfThought" else "highest"


def dspy_helper_ready() -> bool:
    return DSPY_AVAILABLE and bool(COMPILED_MODULE_PATH) and os.path.exists(COMPILED_MODULE_PATH)


def ensure_dspy_helper_trained(model_name: str, base_url: str, force: bool = False) -> str:
    if not DSPY_AVAILABLE:
        return "unavailable"
    if dspy_helper_ready() and not force:
        return "ready"

    lm = dspy.LM(
        f"ollama_chat/{model_name.strip()}",
        api_base=base_url,
        temperature=0.0,
        max_tokens=3000,
    )
    compile_dspy_module(lm)
    return "trained"


def prepare_metadata(
    *,
    final_persona: str,
    final_task: str,
    model_name: str,
    base_url: str,
    generator_mode: str,
    style_sources: list[dict],
    factual_sources: list[dict],
    version_number: int = 1,
    approval_status: str = "draft",
    quality_helper_enabled: bool = False,
    quality_method: str = "ChainOfThought",
) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_package_id": str(uuid.uuid4()),
        "version_number": version_number,
        "approval_status": approval_status,
        "persona": final_persona,
        "task": final_task,
        "model_name": model_name,
        "ollama_base_url": base_url,
        "generator_mode": generator_mode,
        "style_source_count": len([doc for doc in style_sources if not doc.get("error")]),
        "factual_source_count": len([doc for doc in factual_sources if not doc.get("error")]),
        "settings": {
            "quality_helper_enabled": quality_helper_enabled,
            "quality_mode": format_quality_mode(quality_method),
            "prompt_package_version": PROMPT_PACKAGE_VERSION,
        },
    }


def generate_prompt_package(
    *,
    final_persona: str,
    job_role: str,
    final_task: str,
    additional_context: str = "",
    style_brief: str = "",
    factual_brief: str = "",
    style_sources: list[dict] | None = None,
    factual_sources: list[dict] | None = None,
    model_name: str = "llama3.1:latest",
    base_url: str = "http://localhost:11434",
    use_quality_helper: bool = False,
    quality_method: str = "ChainOfThought",
    version_number: int = 1,
    approval_status: str = "draft",
) -> tuple[dict, list[str]]:
    style_sources = style_sources or []
    factual_sources = factual_sources or []
    base_url = base_url.rstrip("/")
    generator_mode = format_generation_style(use_quality_helper and DSPY_AVAILABLE)
    metadata = prepare_metadata(
        final_persona=final_persona,
        final_task=final_task,
        model_name=model_name,
        base_url=base_url,
        generator_mode=generator_mode,
        style_sources=style_sources,
        factual_sources=factual_sources,
        version_number=version_number,
        approval_status=approval_status,
        quality_helper_enabled=use_quality_helper,
        quality_method=quality_method,
    )
    fallback_package = build_fallback_result(
        final_persona,
        job_role,
        final_task,
        additional_context,
        style_brief=style_brief,
        factual_brief=factual_brief,
        style_sources=style_sources,
        factual_sources=factual_sources,
        metadata=metadata,
    )

    validation_errors: list[str] = []
    try:
        if use_quality_helper and DSPY_AVAILABLE:
            method = quality_method
            helper_status = ensure_dspy_helper_trained(model_name, base_url)
            lm = dspy.LM(f"ollama_chat/{model_name}", api_base=base_url, temperature=0.25, max_tokens=3200)
            if method == "BestOfN":
                module = BestOfNModule()
                pred, _ = module.run_all(
                    lm_factory=lambda temp: dspy.LM(f"ollama_chat/{model_name}", api_base=base_url, temperature=temp, max_tokens=3200),
                    persona=final_persona,
                    job_role=job_role,
                    task=final_task,
                    context=additional_context,
                    exemplar_docs=f"STYLE:\n{style_brief}\n\nFACTS:\n{factual_brief}",
                )
            else:
                with dspy.context(lm=lm):
                    module, _ = _load_or_build_module()
                    pred = module(
                        persona=final_persona,
                        job_role=job_role,
                        task=final_task,
                        context=additional_context,
                        exemplar_docs=f"STYLE:\n{style_brief}\n\nFACTS:\n{factual_brief}",
                    )
            package = copy.deepcopy(fallback_package)
            package["persona_analysis"] = getattr(pred, "persona_analysis", package["persona_analysis"]) or package["persona_analysis"]
            package["system_prompt"] = getattr(pred, "system_prompt", package["system_prompt"]) or package["system_prompt"]
            package["user_prompt_template"] = getattr(pred, "user_prompt", package["user_prompt_template"]) or package["user_prompt_template"]
            package["language_notes"] = getattr(pred, "language_notes", package["language_notes"]) or package["language_notes"]
            package["grounding_strategy"] = getattr(pred, "grounding_strategy", package["grounding_strategy"]) or package["grounding_strategy"]
            return finalize_prompt_package(
                package,
                {**metadata, "dspy_helper_status": helper_status},
            ), validation_errors

        generation_prompt = build_generation_prompt(fallback_package, final_persona, job_role, final_task, additional_context, style_brief, factual_brief)
        response = requests.post(
            f"{base_url}/api/generate",
            json={"model": model_name, "prompt": generation_prompt, "stream": False, "options": {"temperature": 0.2}},
            timeout=90,
        )
        response.raise_for_status()
        raw_text = response.json().get("response", "")
        parsed_package, extraction_errors = extract_prompt_package(raw_text)
        validation_errors = extraction_errors + validate_prompt_package(parsed_package) if parsed_package else extraction_errors
        if validation_errors:
            merged_package, repair_notes = merge_prompt_package(parsed_package, fallback_package)
            merged_errors = validate_prompt_package(merged_package)
            if not merged_errors:
                return finalize_prompt_package(
                    merged_package,
                    {**metadata, "generator_mode": "standard (repaired)", "repair_notes": repair_notes},
                ), []

            repair_prompt = build_repair_prompt(parsed_package or {}, fallback_package, validation_errors)
            repair_response = requests.post(
                f"{base_url}/api/generate",
                json={"model": model_name, "prompt": repair_prompt, "stream": False, "options": {"temperature": 0.0}},
                timeout=90,
            )
            repair_response.raise_for_status()
            repaired_raw_text = repair_response.json().get("response", "")
            repaired_package, repair_extraction_errors = extract_prompt_package(repaired_raw_text)
            repaired_package, repair_notes_round_2 = merge_prompt_package(repaired_package, merged_package)
            repaired_errors = repair_extraction_errors + validate_prompt_package(repaired_package)
            if not repaired_errors:
                return finalize_prompt_package(
                    repaired_package,
                    {
                        **metadata,
                        "generator_mode": "standard (second-pass repair)",
                        "repair_notes": repair_notes + repair_notes_round_2,
                    },
                ), []

            package = finalize_prompt_package(
                copy.deepcopy(fallback_package),
                {
                    **metadata,
                    "generator_mode": "fallback after validation issue",
                    "validation_errors": repaired_errors,
                    "repair_notes": repair_notes + repair_notes_round_2,
                },
            )
            return package, repaired_errors

        parsed_package.setdefault("metadata", {})
        if parsed_package.get("prompt_package_version") != PROMPT_PACKAGE_VERSION:
            parsed_package["prompt_package_version"] = PROMPT_PACKAGE_VERSION
        return finalize_prompt_package(parsed_package, metadata), validation_errors
    except Exception as exc:
        package = finalize_prompt_package(
            copy.deepcopy(fallback_package),
            {
                **metadata,
                "generator_mode": "fallback after runtime issue",
                "validation_errors": [str(exc)],
            },
        )
        return package, [str(exc)]
