import json
import re
from copy import deepcopy

from core.fallback_builder import PROMPT_PACKAGE_VERSION

def extract_json_text(text: str) -> str:
    """Extract the most likely JSON object from a model response."""
    cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1]
    return cleaned

def extract_section(text: str, headings: list[str]) -> str:
    """Extract text following one of several headings until the next heading or end of text."""
    lower = text.lower()
    matches = []
    for heading in headings:
        idx = lower.find(heading.lower())
        if idx != -1:
            matches.append((idx, heading))
    if not matches:
        return ""

    start_idx, chosen = min(matches, key=lambda item: item[0])
    remainder = text[start_idx + len(chosen):].lstrip(" :-\n")

    stops = [
        "persona analysis",
        "system prompt",
        "user prompt",
        "language notes",
        "grounding strategy",
    ]
    end_idx = len(remainder)
    for stop in stops:
        if stop.lower() == chosen.lower():
            continue
        pos = remainder.lower().find(stop.lower())
        if pos != -1:
            end_idx = min(end_idx, pos)

    return remainder[:end_idx].strip()

def _maybe_parse_json_value(value):
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    if not cleaned or cleaned[0] not in "[{":
        return value
    try:
        return json.loads(cleaned)
    except Exception:
        return value

def extract_prompt_package(raw: str) -> tuple[dict, list[str]]:
    """Extract a prompt package JSON object from raw model output."""
    errors: list[str] = []
    json_text = extract_json_text(raw)
    try:
        parsed = json.loads(json_text)
    except Exception as exc:
        return {}, [f"Model output is not valid JSON: {exc}"]

    if not isinstance(parsed, dict):
        return {}, ["Model output must be a JSON object."]

    package = parsed.get("prompt_package", parsed)
    if not isinstance(package, dict):
        return {}, ["`prompt_package` must be a JSON object."]

    alias_map = {
        "user_prompt": "user_prompt_template",
        "userPrompt": "user_prompt_template",
        "systemPrompt": "system_prompt",
        "personaAnalysis": "persona_analysis",
        "languageNotes": "language_notes",
        "groundingStrategy": "grounding_strategy",
    }
    for old_key, new_key in alias_map.items():
        if old_key in package and new_key not in package:
            package[new_key] = package[old_key]

    for field in ["input_schema", "output_schema", "safety_policy", "escalation_policy", "acceptance_tests", "metadata"]:
        if field in package:
            package[field] = _maybe_parse_json_value(package[field])

    return package, errors

def _valid_system_prompt(value: str) -> bool:
    text = str(value or "").strip()
    return text.startswith("You are") and len(text.split()) >= 120

def _valid_user_prompt_template(value: str) -> bool:
    text = str(value or "").strip()
    placeholder_matches = re.findall(r"\[([A-Z0-9_]+)\]", text)
    return len(placeholder_matches) >= 5 and ("Provide:" in text or "(1)" in text)

def _valid_output_schema(value: dict) -> bool:
    if not isinstance(value, dict) or value.get("type") != "object":
        return False
    required_output_fields = {"objective_restatement", "deliverable", "risks_and_uncertainties", "source_attribution", "escalation_needed", "final_checklist"}
    return set(value.get("required", []) or []).issuperset(required_output_fields)

def _valid_safety_policy(value: dict) -> bool:
    required_fields = {"allowed_data_sources", "pii_handling", "evidence_rules", "uncertainty_policy", "refusal_triggers", "red_team_checks"}
    return isinstance(value, dict) and required_fields.issubset(set(value.keys()))

def _valid_escalation_policy(value: dict) -> bool:
    required_fields = {"when_to_escalate", "handoff_message"}
    return isinstance(value, dict) and required_fields.issubset(set(value.keys()))

def merge_prompt_package(candidate: dict, fallback: dict) -> tuple[dict, list[str]]:
    """Merge a partial model package into a validated fallback package.

    Keeps model-authored narrative fields when they meet minimum structural rules.
    Falls back to deterministic schema/policy fields when the model omits or weakens them.
    """
    merged = deepcopy(fallback)
    repair_notes: list[str] = []
    if not isinstance(candidate, dict):
        return merged, ["Model package was not an object; used fallback package."]

    for field in ["prompt_package_version", "persona_analysis", "language_notes", "grounding_strategy"]:
        value = candidate.get(field)
        if isinstance(value, str) and value.strip():
            merged[field] = value.strip()

    system_prompt = candidate.get("system_prompt")
    if _valid_system_prompt(system_prompt):
        merged["system_prompt"] = str(system_prompt).strip()
    elif isinstance(system_prompt, str) and system_prompt.strip():
        repair_notes.append("Replaced invalid `system_prompt` with fallback version.")

    user_prompt_template = candidate.get("user_prompt_template") or candidate.get("user_prompt")
    if _valid_user_prompt_template(user_prompt_template):
        merged["user_prompt_template"] = str(user_prompt_template).strip()
    elif isinstance(user_prompt_template, str) and user_prompt_template.strip():
        repair_notes.append("Replaced invalid `user_prompt_template` with fallback version.")

    input_schema = candidate.get("input_schema")
    if isinstance(input_schema, dict) and input_schema.get("type") == "object" and isinstance(input_schema.get("properties"), dict) and isinstance(input_schema.get("required"), list):
        merged["input_schema"] = input_schema
    elif input_schema is not None:
        repair_notes.append("Replaced invalid `input_schema` with fallback version.")

    output_schema = candidate.get("output_schema")
    if _valid_output_schema(output_schema):
        merged["output_schema"] = output_schema
    elif output_schema is not None:
        repair_notes.append("Replaced invalid `output_schema` with fallback version.")

    safety_policy = candidate.get("safety_policy")
    if _valid_safety_policy(safety_policy):
        merged["safety_policy"] = safety_policy
    elif safety_policy is not None:
        repair_notes.append("Replaced invalid `safety_policy` with fallback version.")

    escalation_policy = candidate.get("escalation_policy")
    if _valid_escalation_policy(escalation_policy):
        merged["escalation_policy"] = escalation_policy
    elif escalation_policy is not None:
        repair_notes.append("Replaced invalid `escalation_policy` with fallback version.")

    acceptance_tests = candidate.get("acceptance_tests")
    if isinstance(acceptance_tests, list) and len(acceptance_tests) >= 4:
        merged["acceptance_tests"] = acceptance_tests
    elif acceptance_tests is not None:
        repair_notes.append("Replaced invalid `acceptance_tests` with fallback version.")

    metadata = candidate.get("metadata")
    if isinstance(metadata, dict):
        merged["metadata"].update(metadata)

    return merged, repair_notes

def validate_prompt_package(package: dict) -> list[str]:
    errors: list[str] = []
    required_fields = [
        "prompt_package_version",
        "persona_analysis",
        "system_prompt",
        "user_prompt_template",
        "language_notes",
        "grounding_strategy",
        "input_schema",
        "output_schema",
        "safety_policy",
        "escalation_policy",
        "acceptance_tests",
        "metadata",
    ]
    for field in required_fields:
        if field not in package:
            errors.append(f"Missing required field: {field}")

    if errors:
        return errors

    if str(package.get("prompt_package_version", "")).strip() != PROMPT_PACKAGE_VERSION:
        errors.append(f"`prompt_package_version` must be '{PROMPT_PACKAGE_VERSION}'.")

    system_prompt = str(package.get("system_prompt", "") or "").strip()
    if not system_prompt.startswith("You are"):
        errors.append("`system_prompt` must start with 'You are'.")
    if len(system_prompt.split()) < 120:
        errors.append("`system_prompt` must contain at least 120 words for commercial-grade instruction coverage.")

    user_prompt_template = str(package.get("user_prompt_template", "") or "").strip()
    placeholder_matches = re.findall(r"\[([A-Z0-9_]+)\]", user_prompt_template)
    if len(placeholder_matches) < 5:
        errors.append("`user_prompt_template` must contain at least 5 semantically named [PLACEHOLDER] values.")
    if "Provide:" not in user_prompt_template and "(1)" not in user_prompt_template:
        errors.append("`user_prompt_template` must specify an inline output contract such as 'Provide: (1)...'.")

    input_schema = package.get("input_schema")
    if not isinstance(input_schema, dict) or input_schema.get("type") != "object":
        errors.append("`input_schema` must be a JSON schema object with type 'object'.")
    else:
        if not isinstance(input_schema.get("properties"), dict):
            errors.append("`input_schema.properties` must be an object.")
        if not isinstance(input_schema.get("required"), list):
            errors.append("`input_schema.required` must be a list.")

    output_schema = package.get("output_schema")
    if not isinstance(output_schema, dict) or output_schema.get("type") != "object":
        errors.append("`output_schema` must be a JSON schema object with type 'object'.")
    else:
        required_output_fields = {"objective_restatement", "deliverable", "risks_and_uncertainties", "source_attribution", "escalation_needed", "final_checklist"}
        actual_required = set(output_schema.get("required", []) or [])
        missing_required = sorted(required_output_fields - actual_required)
        if missing_required:
            errors.append(f"`output_schema.required` is missing: {', '.join(missing_required)}")

    safety_policy = package.get("safety_policy")
    if not isinstance(safety_policy, dict):
        errors.append("`safety_policy` must be a JSON object.")
    else:
        for field in ["allowed_data_sources", "pii_handling", "evidence_rules", "uncertainty_policy", "refusal_triggers", "red_team_checks"]:
            if field not in safety_policy:
                errors.append(f"`safety_policy` missing field: {field}")

    escalation_policy = package.get("escalation_policy")
    if not isinstance(escalation_policy, dict):
        errors.append("`escalation_policy` must be a JSON object.")
    else:
        for field in ["when_to_escalate", "handoff_message"]:
            if field not in escalation_policy:
                errors.append(f"`escalation_policy` missing field: {field}")

    acceptance_tests = package.get("acceptance_tests")
    if not isinstance(acceptance_tests, list) or len(acceptance_tests) < 4:
        errors.append("`acceptance_tests` must be a list with at least 4 checks.")

    metadata = package.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("`metadata` must be a JSON object.")
    else:
        for field in ["generated_at", "approval_status", "version_number", "model_name", "generator_mode"]:
            if field not in metadata:
                errors.append(f"`metadata` missing field: {field}")

    return errors

def finalize_prompt_package(package: dict, metadata_overrides: dict | None = None) -> dict:
    package = dict(package)
    package.setdefault("metadata", {})
    if metadata_overrides:
        package["metadata"].update(metadata_overrides)
    package["evaluation"] = evaluate_prompt_package(package)
    return package

def evaluate_prompt_package(package: dict) -> dict:
    system_prompt = str(package.get("system_prompt", "") or "")
    user_prompt = str(package.get("user_prompt_template", "") or "")
    persona_analysis = str(package.get("persona_analysis", "") or "")
    safety_policy = package.get("safety_policy") or {}
    escalation_policy = package.get("escalation_policy") or {}
    output_schema = package.get("output_schema") or {}
    input_schema = package.get("input_schema") or {}
    placeholder_names = set(re.findall(r"\[([A-Z0-9_]+)\]", user_prompt))
    schema_required = {str(name).upper() for name in (input_schema.get("required") or []) if isinstance(name, str)}
    mapped_required = {name.upper() for name in schema_required}
    placeholder_complete = mapped_required.issubset(placeholder_names)
    if "FACTUAL_SOURCES" in mapped_required and ("FACTUAL_SOURCES" in placeholder_names or "FACT_SOURCE_1" in placeholder_names):
        placeholder_complete = (mapped_required - {"FACTUAL_SOURCES"}).issubset(placeholder_names)
    placeholder_detail = "All required schema fields have matching placeholders." if placeholder_complete else "Some required schema fields do not appear as placeholders in the prompt template."

    checks = [
        {
            "label": "System prompt opens with 'You are'",
            "passed": system_prompt.strip().startswith("You are"),
            "detail": "Commercial packages should declare role and scope immediately.",
        },
        {
            "label": "System prompt length ≥ 120 words",
            "passed": len(system_prompt.split()) >= 120,
            "detail": f"{len(system_prompt.split())} words.",
        },
        {
            "label": "Behavioral constraints present",
            "passed": any(token in system_prompt.lower() for token in ["never", "always", "must", "escalate", "if evidence is insufficient"]),
            "detail": "Checks for commercial safety and scope language.",
        },
        {
            "label": "Placeholder completeness",
            "passed": bool(mapped_required) and placeholder_complete,
            "detail": placeholder_detail,
        },
        {
            "label": "Output contract present",
            "passed": "Provide:" in user_prompt or "(1)" in user_prompt,
            "detail": "Prompt should define required sections inline.",
        },
        {
            "label": "Source attribution enforced",
            "passed": "[SOURCE_" in user_prompt or "[SOURCE_ID]" in system_prompt or "source_attribution" in json.dumps(output_schema).lower(),
            "detail": "Required for auditable factual grounding.",
        },
        {
            "label": "Unsupported-domain escalation",
            "passed": isinstance(escalation_policy.get("when_to_escalate"), list) and len(escalation_policy.get("when_to_escalate", [])) >= 3,
            "detail": "Escalation policy should cover out-of-scope or regulated requests.",
        },
        {
            "label": "PII and compliance checks",
            "passed": "pii" in json.dumps(safety_policy).lower() or "personal" in json.dumps(safety_policy).lower(),
            "detail": "Safety policy should address privacy and compliance-sensitive content.",
        },
        {
            "label": "Forbidden-claim protection",
            "passed": "fabricate" in system_prompt.lower() or "fabricate" in json.dumps(safety_policy).lower(),
            "detail": "Package should prohibit fabricated facts, citations, or approvals.",
        },
        {
            "label": "Output schema completeness",
            "passed": isinstance(output_schema, dict) and set(output_schema.get("required", []) or []).issuperset({"objective_restatement", "deliverable", "risks_and_uncertainties", "source_attribution", "escalation_needed", "final_checklist"}),
            "detail": "Checks the downstream deliverable contract.",
        },
        {
            "label": "Persona analysis is substantive",
            "passed": len(persona_analysis.split()) >= 30,
            "detail": f"{len(persona_analysis.split())} words.",
        },
    ]
    passed = sum(1 for check in checks if check["passed"])
    return {
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "score_pct": int((passed / len(checks)) * 100) if checks else 0,
    }

def normalize_result(raw: str):
    """Normalize model output into the expected response structure."""
    parsed = {}
    json_text = extract_json_text(raw)
    try:
        parsed = json.loads(json_text)
    except Exception:
        parsed = {}

    if not isinstance(parsed, dict):
        parsed = {}

    return {
        "persona_analysis": (
            parsed.get("persona_analysis")
            or parsed.get("personaAnalysis")
            or parsed.get("analysis")
            or extract_section(raw, ["persona analysis", "persona-analysis", "analysis"])
        ).strip(),
        "system_prompt": (
            parsed.get("system_prompt")
            or parsed.get("systemPrompt")
            or parsed.get("system")
            or extract_section(raw, ["system prompt", "system-prompt"])
        ).strip(),
        "user_prompt": (
            parsed.get("user_prompt")
            or parsed.get("userPrompt")
            or parsed.get("user")
            or extract_section(raw, ["user prompt", "user-prompt"])
        ).strip(),
        "language_notes": (
            parsed.get("language_notes")
            or parsed.get("languageNotes")
            or parsed.get("notes")
            or extract_section(raw, ["language notes", "domain language choices", "notes"])
        ).strip(),
        "grounding_strategy": (
            parsed.get("grounding_strategy")
            or parsed.get("groundingStrategy")
            or parsed.get("grounding")
            or extract_section(raw, ["grounding strategy", "grounding"])
        ).strip(),
        "raw": raw,
    }

def merge_result(primary: dict, fallback: dict) -> dict:
    merged = fallback.copy()
    for key, value in primary.items():
        if key in merged and isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged

def score_prompt_quality(r: dict) -> list[dict]:
    """Score a result dict against 6 structural quality criteria.
    Returns a list of {label, passed, detail} dicts.
    """
    sp = r.get("system_prompt", "") or ""
    up = r.get("user_prompt", "") or ""
    pa = r.get("persona_analysis", "") or ""
    constraint_words = ["never", "always", "must", "do not", "avoid", "flag", "escalate"]
    structure_words  = ["provide:", "(1)", "outline", "list", "summarize", "detail"]
    checks = [
        {
            "label": "System prompt opens with 'You are'",
            "passed": sp.strip().startswith("You are"),
            "detail": "Should start with 'You are [specific professional title]'",
        },
        {
            "label": "System prompt length ≥ 80 words",
            "passed": len(sp.split()) >= 80,
            "detail": f"{len(sp.split())} words — target 120–250",
        },
        {
            "label": "Contains behavioral constraints",
            "passed": any(w in sp.lower() for w in constraint_words),
            "detail": "Should include constraint language: never / always / must / flag / escalate",
        },
        {
            "label": "User prompt has [PLACEHOLDER] slots",
            "passed": "[" in up and "]" in up,
            "detail": "Semantically named placeholders like [CASE_FACTS] or [JURISDICTION]",
        },
        {
            "label": "User prompt specifies output structure",
            "passed": any(w in up.lower() for w in structure_words),
            "detail": "Should include inline structure e.g. 'Provide: (1)..., (2)..., (3)...'",
        },
        {
            "label": "Persona analysis is substantive",
            "passed": len(pa.split()) >= 20,
            "detail": f"{len(pa.split())} words — target 30–60",
        },
    ]
    return checks
