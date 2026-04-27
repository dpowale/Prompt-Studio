from __future__ import annotations

import copy
from datetime import datetime, timezone


PROMPT_PACKAGE_VERSION = "2.0"


def _clean(value: str) -> str:
    return (value or "").strip()


def build_persona_analysis(final_persona: str, job_role: str, style_brief: str, factual_brief: str) -> str:
    base = (
        f"{final_persona} operates as a domain specialist whose reasoning should reflect the workflow, risk posture, and evidence standards of {job_role.strip().rstrip('.') or final_persona}. "
        "The prompts should force the downstream model to distinguish verified facts from assumptions, disclose uncertainty when evidence is incomplete, and stay within the persona's legitimate scope. "
        "Responses should be practical enough for business use, but conservative about unsupported claims, compliance-sensitive topics, and high-risk edge cases."
    )
    if style_brief:
        base += " Style grounding is available and should influence register, terminology density, and document structure."
    if factual_brief:
        base += " Factual grounding is available and should be cited using explicit source identifiers rather than implied knowledge."
    return base


def build_system_prompt(
    final_persona: str,
    job_role: str,
    final_task: str,
    additional_context: str,
    style_brief: str,
    factual_brief: str,
) -> str:
    role_scope = job_role.strip().rstrip(".") or f"the professional standards of a {final_persona}"
    context_clause = f" Additional business constraints: {additional_context.strip()}" if _clean(additional_context) else ""
    style_clause = (
        "Use approved style guidance and uploaded style references only to shape tone, terminology, and document structure."
        if style_brief
        else "No style references were supplied, so default to clear, formal, commercially appropriate language for the stated persona."
    )
    factual_clause = (
        "Use only user-provided facts and approved factual reference sources labeled as [SOURCE_ID]. When evidence is insufficient or conflicting, state that explicitly instead of inferring unsupported facts."
        if factual_brief
        else "Operate only on user-provided facts. If the request requires evidence that is not present, state the gap plainly and ask for the missing material."
    )
    return (
        f"You are a Senior Prompt Architect designing production-ready prompts for a {final_persona}. Your scope is to translate the working norms of {role_scope} into prompts that are safe for commercial use while helping the downstream model {final_task.lower()}. "
        "You must encode role boundaries, accepted evidence standards, output structure, uncertainty handling, and escalation rules directly into the prompt package. "
        f"{style_clause} {factual_clause} "
        "Always require the downstream model to cite factual claims to [SOURCE_ID] references when such sources are available, separate facts from assumptions, and surface any ambiguity, missing evidence, policy risk, or compliance concern before giving a conclusion. "
        "Never fabricate authorities, customer data, metrics, or domain conclusions. Never present legal, medical, financial, HR, or security guidance as definitive if the request is outside scope, missing evidence, or requires licensed review. "
        "If the request touches regulated advice, personal data, contractual commitments, safety-critical decisions, or unsupported claims, instruct the downstream model to pause, flag the risk, and recommend escalation to a qualified human reviewer. "
        "Require an output contract with labeled sections, concise reasoning, and a final checklist confirming grounding, compliance, and unresolved risks."
        f"{context_clause}"
    )


def build_user_prompt(
    final_persona: str,
    job_role: str,
    final_task: str,
    additional_context: str,
    style_brief: str,
    factual_brief: str,
) -> str:
    role_scope = job_role.strip().rstrip(".") or final_persona
    lines = [
        f"Act as a {final_persona} operating within this role context: {role_scope}.",
        f"Primary objective: {final_task}.",
        "Use these inputs: [TASK_GOAL], [INPUT_CONTENT], [CONSTRAINTS], [OUTPUT_AUDIENCE], and [DELIVERABLE_FORMAT].",
        "If style guidance is available, use [STYLE_GUIDE] to mirror terminology, cadence, formatting, and brand voice without copying source text verbatim.",
        "If factual sources are available, use [FACTUAL_SOURCES], [FACT_SOURCE_1], [FACT_SOURCE_2], and additional [SOURCE_ID] references as the only grounds for factual claims.",
    ]
    if _clean(additional_context):
        lines.append(f"Business constraints already supplied: {additional_context.strip()}")
    if style_brief:
        lines.append("Style grounding is available and should influence tone, heading structure, and vocabulary choice.")
    if factual_brief:
        lines.append("Factual grounding is available; cite factual statements inline as [SOURCE_ID] and explicitly label assumptions as assumptions.")
    lines.extend(
        [
            "Provide: (1) a brief objective restatement, (2) a grounded deliverable that follows [DELIVERABLE_FORMAT], (3) a section called Risks and Uncertainties, (4) a section called Source Attribution listing the [SOURCE_ID] items used, and (5) a section called Escalation Needed if any requested action exceeds the available evidence or professional scope.",
            "Do not invent data, citations, policies, precedents, or customer-specific facts. If required inputs are missing, say exactly what is missing before continuing.",
        ]
    )
    return "\n".join(lines).strip()


def build_language_notes(final_persona: str, job_role: str, style_brief: str, factual_brief: str) -> str:
    notes = [
        f"Used the terminology and point of view of {final_persona} rather than generic assistant language.",
        f"Anchored obligations to {job_role.strip().rstrip('.') or final_persona} so the prompts preserve real-world scope boundaries.",
        "Added explicit grounding language so factual claims must point to provided sources instead of model memory.",
        "Added uncertainty and escalation phrasing to reduce commercial risk from unsupported conclusions.",
        "Added compliance-oriented wording around personal data, regulated advice, and business commitments.",
    ]
    if style_brief:
        notes.append("Style references were summarized into reusable guidance on cadence, register, and formatting rather than copied verbatim.")
    if factual_brief:
        notes.append("Factual references are framed as cited evidence sources so downstream outputs can be audited later.")
    return " ".join(notes)


def build_grounding_strategy(style_brief: str, factual_brief: str, style_sources: list[dict], factual_sources: list[dict]) -> str:
    style_count = len([doc for doc in style_sources or [] if not doc.get("error")])
    factual_count = len([doc for doc in factual_sources or [] if not doc.get("error")])
    parts = []
    if style_brief:
        parts.append(
            f"Style grounding used {style_count or 'manual'} approved references to infer tone, heading patterns, terminology density, and brand-adjacent phrasing without copying source passages."
        )
    if factual_brief:
        parts.append(
            f"Factual grounding used {factual_count or 'manual'} approved references and requires downstream claims to cite the relevant [SOURCE_ID] values explicitly."
        )
    if not parts:
        parts.append("No external grounding was provided. The prompts are grounded only in the persona, task, and stated constraints.")
    return " ".join(parts)


def build_input_schema(style_sources: list[dict], factual_sources: list[dict]) -> dict:
    properties = {
        "task_goal": {"type": "string", "description": "What the downstream model must accomplish."},
        "input_content": {"type": "string", "description": "Primary working material provided by the end user."},
        "constraints": {"type": "string", "description": "Business rules, tone limits, or formatting constraints."},
        "output_audience": {"type": "string", "description": "Who the final deliverable is for."},
        "deliverable_format": {"type": "string", "description": "Requested format such as memo, email, report, checklist, or table."},
        "style_guide": {"type": "string", "description": "Optional style guidance or tone rules."},
        "factual_sources": {
            "type": "array",
            "description": "Optional evidence sources that may be cited in the final answer.",
            "items": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["source_id", "content"],
            },
        },
    }
    required = ["task_goal", "input_content", "constraints", "output_audience", "deliverable_format"]
    if style_sources:
        required.append("style_guide")
    if factual_sources:
        required.append("factual_sources")
    return {"type": "object", "properties": properties, "required": required}


def build_output_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "objective_restatement": {"type": "string"},
            "deliverable": {"type": "string"},
            "risks_and_uncertainties": {"type": "array", "items": {"type": "string"}},
            "source_attribution": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_id": {"type": "string"},
                        "usage_note": {"type": "string"},
                    },
                    "required": ["source_id", "usage_note"],
                },
            },
            "escalation_needed": {"type": "string"},
            "final_checklist": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "objective_restatement",
            "deliverable",
            "risks_and_uncertainties",
            "source_attribution",
            "escalation_needed",
            "final_checklist",
        ],
    }


def build_safety_policy(final_persona: str, factual_sources: list[dict]) -> dict:
    return {
        "allowed_data_sources": [
            "User-provided inputs",
            "Approved style guidance",
            "Approved factual references labeled [SOURCE_ID]",
        ],
        "pii_handling": "Do not expose, transform, or infer personal, confidential, or client-sensitive data beyond the user's explicit request. Redact or generalize sensitive details when possible.",
        "evidence_rules": "Treat model memory as unverified. All factual claims must come from user input or cited [SOURCE_ID] references.",
        "uncertainty_policy": "When evidence is incomplete, contradictory, or missing, say so directly and ask for additional material rather than inventing details.",
        "refusal_triggers": [
            "Requests to fabricate evidence, citations, metrics, or approvals",
            "Requests that require licensed legal, medical, financial, HR, or security sign-off without adequate source support",
            "Requests to reveal secrets, credentials, private data, or regulated content without authorization",
        ],
        "red_team_checks": [
            "Check for unsupported claims or hidden assumptions",
            "Check for policy, privacy, and compliance exposure",
            "Check whether the requested action exceeds the stated role scope",
        ],
        "source_requirement": "Inline source attribution is mandatory when factual sources are present." if factual_sources else "No factual source files were uploaded; only user-provided facts may be used.",
        "persona_scope": f"The downstream model must stay within the working scope of {final_persona} and avoid claiming licensed authority it does not have.",
    }


def build_escalation_policy(final_persona: str) -> dict:
    return {
        "when_to_escalate": [
            "The request would create legal, medical, financial, employment, safety, or security commitments",
            "Evidence is missing, contradictory, or too weak to support a confident answer",
            "The output would expose sensitive data or create a compliance obligation",
            "The request exceeds the normal professional scope of the selected persona",
        ],
        "handoff_message": f"Escalate to a qualified human reviewer when the request exceeds the supported scope of a {final_persona} or when the evidence base is incomplete.",
    }


def build_acceptance_tests() -> list[dict]:
    return [
        {"id": "AT-1", "description": "System prompt starts with 'You are' and defines role scope, grounding, uncertainty, and escalation behavior."},
        {"id": "AT-2", "description": "User prompt template contains semantically named [PLACEHOLDER] values for goal, inputs, constraints, audience, and deliverable format."},
        {"id": "AT-3", "description": "Prompt package requires factual claims to cite [SOURCE_ID] references when factual grounding is present."},
        {"id": "AT-4", "description": "Prompt package includes refusal rules for fabricated evidence, privacy violations, and unsupported regulated advice."},
        {"id": "AT-5", "description": "Expected output contract contains objective restatement, deliverable, risks, source attribution, escalation, and final checklist sections."},
    ]


def build_prompt_package(
    final_persona: str,
    job_role: str,
    final_task: str,
    additional_context: str,
    style_brief: str = "",
    factual_brief: str = "",
    style_sources: list[dict] | None = None,
    factual_sources: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    style_sources = style_sources or []
    factual_sources = factual_sources or []
    package = {
        "prompt_package_version": PROMPT_PACKAGE_VERSION,
        "persona_analysis": build_persona_analysis(final_persona, job_role, style_brief, factual_brief),
        "system_prompt": build_system_prompt(final_persona, job_role, final_task, additional_context, style_brief, factual_brief),
        "user_prompt_template": build_user_prompt(final_persona, job_role, final_task, additional_context, style_brief, factual_brief),
        "language_notes": build_language_notes(final_persona, job_role, style_brief, factual_brief),
        "grounding_strategy": build_grounding_strategy(style_brief, factual_brief, style_sources, factual_sources),
        "input_schema": build_input_schema(style_sources, factual_sources),
        "output_schema": build_output_schema(),
        "safety_policy": build_safety_policy(final_persona, factual_sources),
        "escalation_policy": build_escalation_policy(final_persona),
        "acceptance_tests": build_acceptance_tests(),
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "approval_status": "draft",
            "version_number": 1,
        },
    }
    if metadata:
        package["metadata"].update(copy.deepcopy(metadata))
    return package


def build_fallback_result(
    final_persona: str,
    job_role: str,
    final_task: str,
    additional_context: str,
    style_brief: str = "",
    factual_brief: str = "",
    style_sources: list[dict] | None = None,
    factual_sources: list[dict] | None = None,
    metadata: dict | None = None,
):
    return build_prompt_package(
        final_persona=final_persona,
        job_role=job_role,
        final_task=final_task,
        additional_context=additional_context,
        style_brief=style_brief,
        factual_brief=factual_brief,
        style_sources=style_sources,
        factual_sources=factual_sources,
        metadata=metadata,
    )
