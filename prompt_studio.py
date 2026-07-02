import copy
import hashlib
import html
import json
import os
import uuid
from datetime import datetime, timezone

import requests
import streamlit as st

try:
    import dspy

    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

from core.fallback_builder import PROMPT_PACKAGE_VERSION, build_fallback_result
from core.grounding import MAX_GROUNDING_DOCUMENTS, SUPPORTED_UPLOAD_TYPES, build_grounding_brief, extract_grounding_documents
from core.llm_api import fetch_ollama_models
from core.prompt_library import count_prompts as count_library_prompts, list_prompts as list_library_prompts, save_package_to_library
from core.utils import evaluate_prompt_package, extract_prompt_package, finalize_prompt_package, merge_prompt_package, validate_prompt_package
from ui.components import copy_button_html
from ui.theme import THEME_PRESETS, theme_css

if DSPY_AVAILABLE:
    from core.dspy_module import COMPILED_MODULE_PATH, BestOfNModule, _load_or_build_module, compile_dspy_module


st.set_page_config(page_title="Prompt Studio", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

PERSONAS = {
    "Healthcare Expert (Doctor/Clinician)": ("doctor", "Healthcare"),
    "Legal Professional (Attorney/Counsel)": ("lawyer", "Legal"),
    "Financial Analyst": ("analyst", "Finance"),
    "IT Professional (Software Engineer)": ("engineer", "Technology"),
    "Researcher": ("researcher", "Research"),
    "Marketing Strategist": ("marketer", "Marketing"),
    "HR Professional": ("hr", "Human Resources"),
    "Write Your Own (Custom)": ("custom", "Custom"),
}

TASKS = [
    "Summarize complex documents",
    "Draft professional emails or letters",
    "Analyze data and generate insights",
    "Review and critique content",
    "Provide expert recommendations",
    "Custom task...",
]


def init_session_state() -> None:
    defaults = {
        "current_step": 1,
        "theme_mode": "Light",
        "ollama_base_url": "http://localhost:11434",
        "prompt_package": None,
        "prompt_history": [],
        "validation_errors": [],
        "style_guide_notes": "",
        "factual_reference_notes": "",
        "style_source_catalog": [],
        "factual_source_catalog": [],
        "style_upload_signature": "",
        "factual_upload_signature": "",
        "approval_status": "draft",
        "load_ver": 0,
        "dspy_mode": DSPY_AVAILABLE,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


@st.cache_data(ttl=30, show_spinner=False)
def fetch_cached_ollama_models(base_url: str) -> list[str]:
    return fetch_ollama_models(base_url)


@st.cache_data(show_spinner=False)
def extract_cached_grounding_documents(file_payloads: tuple[tuple[str, bytes], ...], kind: str) -> list[dict]:
    class UploadedFileShim:
        def __init__(self, name: str, data: bytes):
            self.name = name
            self._data = data

        def getvalue(self):
            return self._data

    uploads = [UploadedFileShim(name, data) for name, data in file_payloads]
    return extract_grounding_documents(uploads, kind)


def build_upload_signature(uploaded_files) -> str:
    if not uploaded_files:
        return ""

    digest = hashlib.sha256()
    for uploaded_file in uploaded_files:
        name = getattr(uploaded_file, "name", "unnamed")
        data = uploaded_file.getvalue()
        digest.update(name.encode("utf-8", errors="ignore"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def build_file_payloads(uploaded_files) -> tuple[tuple[str, bytes], ...]:
    if not uploaded_files:
        return tuple()
    return tuple((getattr(uploaded_file, "name", "unnamed"), uploaded_file.getvalue()) for uploaded_file in uploaded_files)


def render_source_catalog(title: str, sources: list[dict]) -> None:
    st.markdown(f"#### {title}")
    if not sources:
        st.caption("No uploaded documents yet.")
        return
    for source in sources:
        label = f"{source.get('source_id', 'SOURCE_UNKNOWN')} — {source.get('name', 'unnamed')}"
        if source.get("error"):
            with st.expander(label):
                st.error(source["error"])
            continue
        with st.expander(label):
            st.caption(f"{source.get('char_count', 0)} chars • {source.get('chunk_count', 0)} chunks")
            st.write(source.get("summary") or "No summary available.")


def build_generation_prompt(template_package: dict, final_persona: str, job_role: str, final_task: str, additional_context: str, style_brief: str, factual_brief: str) -> str:
    return f"""
Return one JSON object only. Do not use markdown fences. The object must validate exactly against the structure and data types shown in the schema example below.

Schema example:
{json.dumps(template_package, indent=2)}

Now generate a new commercial-grade prompt package for these inputs:
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


def format_generation_mode(use_dspy: bool) -> str:
    return "quality helper" if use_dspy else "standard"


def format_quality_mode(method: str) -> str:
    return "balanced" if method == "ChainOfThought" else "highest"


def dspy_helper_ready() -> bool:
    return DSPY_AVAILABLE and os.path.exists(COMPILED_MODULE_PATH)


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


def prepare_metadata(final_persona: str, final_task: str, model_name: str, base_url: str, generator_mode: str, style_sources: list[dict], factual_sources: list[dict]) -> dict:
    version_number = len(st.session_state.get("prompt_history", [])) + 1
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_package_id": str(uuid.uuid4()),
        "version_number": version_number,
        "approval_status": st.session_state.get("approval_status", "draft"),
        "persona": final_persona,
        "task": final_task,
        "model_name": model_name,
        "ollama_base_url": base_url,
        "generator_mode": generator_mode,
        "style_source_count": len([doc for doc in style_sources if not doc.get("error")]),
        "factual_source_count": len([doc for doc in factual_sources if not doc.get("error")]),
        "settings": {
            "quality_helper_enabled": st.session_state.get("dspy_mode", False),
            "quality_mode": format_quality_mode(st.session_state.get("dspy_method", "ChainOfThought")),
            "prompt_package_version": PROMPT_PACKAGE_VERSION,
        },
    }


def store_package(package: dict, validation_errors: list[str]) -> None:
    st.session_state["prompt_package"] = copy.deepcopy(package)
    st.session_state["validation_errors"] = list(validation_errors)
    history = st.session_state.get("prompt_history", [])
    history.append(copy.deepcopy(package))
    st.session_state["prompt_history"] = history
    st.session_state["approval_status"] = package.get("metadata", {}).get("approval_status", "draft")


def sync_approval_status(selected_status: str) -> None:
    package = st.session_state.get("prompt_package")
    if not package:
        return
    package["metadata"]["approval_status"] = selected_status
    st.session_state["approval_status"] = selected_status
    history = st.session_state.get("prompt_history", [])
    if history and history[-1].get("metadata", {}).get("prompt_package_id") == package.get("metadata", {}).get("prompt_package_id"):
        history[-1]["metadata"]["approval_status"] = selected_status
        st.session_state["prompt_history"] = history


WIZARD_INPUT_KEYS = (
    "persona_choice",
    "custom_persona_name",
    "job_role",
    "task_choice",
    "custom_task",
    "additional_context",
    "style_guide_notes",
    "factual_reference_notes",
    "style_source_catalog",
    "factual_source_catalog",
    "style_upload_signature",
    "factual_upload_signature",
    "prompt_package",
    "validation_errors",
    "approval_status",
)


def reset_for_new_prompt(*, clear_history: bool = False) -> None:
    """Clear wizard inputs and the current result so the user can build a fresh prompt.

    Keeps app-level settings (theme, model, Ollama URL), the saved prompt library, and
    — unless ``clear_history`` is set — the in-session package history. Bumping
    ``load_ver`` resets the keyed input widgets back to their defaults.
    """
    for key in WIZARD_INPUT_KEYS:
        st.session_state.pop(key, None)
    if clear_history:
        st.session_state["prompt_history"] = []
    st.session_state["current_step"] = 1
    st.session_state["load_ver"] = st.session_state.get("load_ver", 0) + 1


def render_hero_section() -> None:
        st.markdown(
                """
                <div class='hero-shell'>
                    <div class='hero-title'>Prompt Studio</div>
                    <div class='hero-subtitle'>Build grounded prompt packages with auditable structure, source-aware instructions, and reusable governance metadata</div>
                </div>
                """,
                unsafe_allow_html=True,
        )


def render_stepper(current_step: int) -> None:
    steps = [
        (1, "Persona", "Choose the expert role and working scope."),
        (2, "Task & Grounding", "Add the task, constraints, and reference material."),
        (3, "Review & Generate", "Create, review, and export the final package."),
    ]
    cols = st.columns(3)
    for col, (number, title, note) in zip(cols, steps):
        state_class = "active" if current_step == number else "done" if current_step > number else ""
        state_text = "Current" if current_step == number else "Complete" if current_step > number else "Up next"
        with col:
            st.markdown(
                f"""
                <div class='step-card {state_class}'>
                    <div class='step-label'>Step {number} <span class='step-status'>• {state_text}</span></div>
                    <div class='step-name'>{html.escape(title)}</div>
                    <div class='step-note'>{html.escape(note)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.progress(current_step / 3.0)


def render_section_intro(kicker: str, title: str, body: str) -> None:
        st.markdown(
                f"""
                <div class='section-card'>
                    <div class='section-kicker'>{html.escape(kicker)}</div>
                    <div class='section-title'>{html.escape(title)}</div>
                    <div class='section-body'>{html.escape(body)}</div>
                </div>
                """,
                unsafe_allow_html=True,
        )


def render_helper_card(title: str, body: str) -> None:
        st.markdown(
                f"""
                <div class='helper-card'>
                    <div class='helper-title'>{html.escape(title)}</div>
                    <div class='helper-body'>{html.escape(body)}</div>
                </div>
                """,
                unsafe_allow_html=True,
        )


def render_mini_cards(items: list[tuple[str, str]]) -> None:
    columns = st.columns(len(items))
    for column, (label, value) in zip(columns, items):
        with column:
            with st.container(border=True):
                st.caption(label.upper())
                st.markdown(f"**{html.escape(value)}**")


def render_score_card(evaluation: dict) -> None:
    passed = int(evaluation.get("passed", 0) or 0)
    total = int(evaluation.get("total", 0) or 0)
    score_pct = int(evaluation.get("score_pct", 0) or 0)
    bounded_score = max(0, min(score_pct, 100))
    with st.container(border=True):
        left_col, right_col = st.columns([4, 1])
        with left_col:
            st.markdown("### Readiness Score")
            st.caption(f"Passed {passed}/{total} validation checks across structure, grounding, and safety.")
        with right_col:
            st.metric("Score", f"{bounded_score}%")
        st.progress(bounded_score / 100)


init_session_state()

with st.sidebar:
    st.markdown(
        """
        <div style='padding: 0.5rem 0 1.25rem'>
          <div style='font-size:0.65rem; letter-spacing:0.3em; text-transform:uppercase; color:var(--accent-color); margin-bottom:0.4rem;'>App Tools</div>
                    <div style='font-size:1.15rem; font-weight:600; color:var(--text-color);'>Prompt Studio</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    theme_mode = st.selectbox(
        "App Theme",
        list(THEME_PRESETS.keys()),
        index=list(THEME_PRESETS.keys()).index(st.session_state.get("theme_mode", "Light")) if st.session_state.get("theme_mode", "Light") in THEME_PRESETS else 1,
    )
    st.session_state["theme_mode"] = theme_mode

    st.markdown("---")
    if st.button("➕ Start New Prompt", use_container_width=True, help="Clear the current inputs and result to build a fresh prompt. Saved library prompts are kept."):
        reset_for_new_prompt()
        st.rerun()

    st.markdown("---")
    with st.expander("Advanced AI Options", expanded=False):
        ollama_base_url = st.text_input("Ollama URL (Local AI Engine)", value=st.session_state.get("ollama_base_url", "http://localhost:11434"))
        st.session_state["ollama_base_url"] = ollama_base_url.rstrip("/")

        try:
            ollama_models = fetch_cached_ollama_models(st.session_state["ollama_base_url"])
        except Exception:
            ollama_models = []
            st.error("Cannot connect to local AI Engine. Make sure Ollama is running.")

        default_model = ollama_models[0] if ollama_models else "llama3.1:latest"
        st.session_state.setdefault("ollama_selected_model", default_model)

        if ollama_models:
            selected_index = ollama_models.index(st.session_state["ollama_selected_model"]) if st.session_state["ollama_selected_model"] in ollama_models else 0
            st.session_state["ollama_selected_model"] = st.selectbox("AI Model to use:", ollama_models, index=selected_index)
        else:
            st.session_state["ollama_selected_model"] = st.text_input("AI Model to use:", value=st.session_state.get("ollama_selected_model", default_model))

        if DSPY_AVAILABLE:
            st.session_state["dspy_mode"] = st.toggle("Use DSPy to improve prompt writing (recommended)", value=st.session_state.get("dspy_mode", True))
            if st.session_state["dspy_mode"]:
                st.caption("DSPy can improve wording and structure, but generation may take a little longer.")
                method_choice = st.radio(
                    "Generation style",
                    ["Balanced quality (faster)", "Highest quality (slower)"],
                    index=0 if st.session_state.get("dspy_method", "ChainOfThought") == "ChainOfThought" else 1,
                )
                st.session_state["dspy_method"] = "ChainOfThought" if "faster" in method_choice else "BestOfN"
                if dspy_helper_ready():
                    st.caption("DSPy helper is ready. You can retrain it any time if you want to refresh saved examples.")
                else:
                    st.caption("On your first DSPy generation, the app will automatically train the DSPy helper for you.")
                train_button_label = "Retrain DSPy helper" if dspy_helper_ready() else "Train DSPy helper now"
                if st.button(train_button_label):
                    with st.spinner("Training DSPy helper..."):
                        ensure_dspy_helper_trained(st.session_state["ollama_selected_model"], st.session_state["ollama_base_url"], force=True)
                        st.success("DSPy helper trained successfully.")
        else:
            st.warning("DSPy is not installed. The app will use standard generation instead.")

    st.markdown("---")
    st.markdown("### Save / Load Progress")
    state_to_save = {
        "current_step": st.session_state.get("current_step", 1),
        "persona_choice": st.session_state.get("persona_choice"),
        "custom_persona_name": st.session_state.get("custom_persona_name"),
        "job_role": st.session_state.get("job_role"),
        "task_choice": st.session_state.get("task_choice"),
        "custom_task": st.session_state.get("custom_task"),
        "additional_context": st.session_state.get("additional_context"),
        "style_guide_notes": st.session_state.get("style_guide_notes", ""),
        "factual_reference_notes": st.session_state.get("factual_reference_notes", ""),
        "style_source_catalog": st.session_state.get("style_source_catalog", []),
        "factual_source_catalog": st.session_state.get("factual_source_catalog", []),
        "theme_mode": st.session_state.get("theme_mode"),
        "ollama_selected_model": st.session_state.get("ollama_selected_model"),
        "ollama_base_url": st.session_state.get("ollama_base_url"),
        "prompt_package": st.session_state.get("prompt_package"),
        "prompt_history": st.session_state.get("prompt_history", []),
        "approval_status": st.session_state.get("approval_status", "draft"),
        "validation_errors": st.session_state.get("validation_errors", []),
    }
    st.download_button("Save Project", data=json.dumps(state_to_save, indent=2), file_name="prompt_builder_save.json", mime="application/json", use_container_width=True)

    uploaded_state = st.file_uploader("Load Project", type=["json"], label_visibility="collapsed")
    if uploaded_state is not None:
        upload_hash = hash(uploaded_state.getvalue())
        if st.session_state.get("last_uploaded_hash") != upload_hash:
            st.session_state["last_uploaded_hash"] = upload_hash
            try:
                imported = json.loads(uploaded_state.getvalue().decode("utf-8"))
                if imported.get("result") and not imported.get("prompt_package"):
                    imported["prompt_package"] = imported.get("result")
                for key, value in imported.items():
                    if value is not None:
                        st.session_state[key] = value
                st.session_state["current_step"] = 1
                st.session_state["load_ver"] = st.session_state.get("load_ver", 0) + 1
                st.success("Project loaded successfully.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to load project: {exc}")

st.markdown(theme_css(st.session_state.get("theme_mode", "Light")), unsafe_allow_html=True)
render_hero_section()

current_step = st.session_state.get("current_step", 1)
render_stepper(current_step)

persona_choice = st.session_state.get("persona_choice", list(PERSONAS.keys())[0])
custom_persona_name = st.session_state.get("custom_persona_name", "")
job_role = st.session_state.get("job_role", "")
task_choice = st.session_state.get("task_choice", TASKS[0])
custom_task = st.session_state.get("custom_task", "")
additional_context = st.session_state.get("additional_context", "")
style_guide_notes = st.session_state.get("style_guide_notes", "")
factual_reference_notes = st.session_state.get("factual_reference_notes", "")
load_ver = st.session_state.get("load_ver", 0)

if current_step == 1:
    render_section_intro(
        "Step 1",
        "Choose the professional persona",
        "Select the expert point of view you want the prompt package to reflect, then describe how that role usually works.",
    )
    safe_persona_index = list(PERSONAS.keys()).index(persona_choice) if persona_choice in PERSONAS else 0
    persona_choice = st.radio("Select an Expert Role:", list(PERSONAS.keys()), index=safe_persona_index, key=f"persona_choice_{load_ver}")
    st.session_state["persona_choice"] = persona_choice
    if "Custom" in persona_choice:
        custom_persona_name = st.text_input("Enter the Expert's Title:", value=custom_persona_name, placeholder="Example: Health and Safety Inspector", key=f"custom_persona_name_{load_ver}")
        st.session_state["custom_persona_name"] = custom_persona_name
    job_role = st.text_area("What are their day-to-day responsibilities?", value=job_role, height=110, placeholder="Example: Reviews safety compliance, writes incident reports, drafts remediation guidance...", key=f"job_role_{load_ver}")
    st.session_state["job_role"] = job_role
    needs_custom_title = "Custom" in persona_choice and not custom_persona_name.strip()
    persona_ready = not needs_custom_title
    if needs_custom_title:
        st.caption("Enter the expert's title to continue.")
    elif not job_role.strip():
        st.caption("Tip: describing the day-to-day responsibilities improves the result, but it's optional — you can continue now.")
    if st.button("Continue to Step 2 →", type="primary", use_container_width=True, disabled=not persona_ready):
        st.session_state["current_step"] = 2
        st.rerun()

elif current_step == 2:
    render_section_intro(
        "Step 2",
        "Describe the task and add reference material",
        "Tell the app what you need, add any limits or formatting rules, and optionally upload examples or source material.",
    )
    with st.container(border=True):
        st.markdown("#### 1. Task")
        safe_task_index = TASKS.index(task_choice) if task_choice in TASKS else len(TASKS) - 1
        task_choice = st.selectbox("What should the prompt help with?", TASKS, index=safe_task_index, key=f"task_choice_{load_ver}")
        st.session_state["task_choice"] = task_choice
        if task_choice == "Custom task...":
            custom_task = st.text_input("Describe the task", value=custom_task, placeholder="Example: Draft a customer-ready incident response summary.", key=f"custom_task_{load_ver}")
            st.session_state["custom_task"] = custom_task

        additional_context = st.text_area(
            "Rules, formatting needs, or constraints",
            value=additional_context,
            height=90,
            placeholder="Example: Keep it under 250 words, cite the policy source, and flag unresolved risks.",
            key=f"additional_context_{load_ver}",
        )
        st.session_state["additional_context"] = additional_context

    style_col, factual_col = st.columns(2)

    with style_col:
        with st.container(border=True):
            st.markdown("#### 2. Optional writing examples")
            st.caption("Use this when you want the output to match a certain tone, structure, or voice.")
            style_guide_notes = st.text_area(
                "Writing style notes",
                value=style_guide_notes,
                height=110,
                placeholder="Example: Sound like a concise policy memo. Use short paragraphs and plain language.",
                key=f"style_notes_{load_ver}",
            )
            st.session_state["style_guide_notes"] = style_guide_notes
            style_uploads = st.file_uploader(
                "Upload writing examples",
                type=SUPPORTED_UPLOAD_TYPES,
                accept_multiple_files=True,
                key=f"style_uploads_{load_ver}",
            )
            if style_uploads:
                if len(style_uploads) > MAX_GROUNDING_DOCUMENTS:
                    st.warning(f"Only the first {MAX_GROUNDING_DOCUMENTS} writing examples will be used.")
                style_upload_signature = build_upload_signature(style_uploads)
                if st.session_state.get("style_upload_signature") != style_upload_signature:
                    st.session_state["style_source_catalog"] = extract_cached_grounding_documents(
                        build_file_payloads(style_uploads),
                        "style",
                    )
                    st.session_state["style_upload_signature"] = style_upload_signature
            elif st.session_state.get("style_upload_signature"):
                st.session_state["style_upload_signature"] = ""
                st.session_state["style_source_catalog"] = []
            render_source_catalog("Writing examples", st.session_state.get("style_source_catalog", []))

    with factual_col:
        with st.container(border=True):
            st.markdown("#### 3. Optional source material")
            st.caption("Use this when the response must rely on approved facts or source documents.")
            factual_reference_notes = st.text_area(
                "Fact notes",
                value=factual_reference_notes,
                height=110,
                placeholder="Example: Internal policy summary, approved pricing language, or customer requirements.",
                key=f"factual_notes_{load_ver}",
            )
            st.session_state["factual_reference_notes"] = factual_reference_notes
            factual_uploads = st.file_uploader(
                "Upload source material",
                type=SUPPORTED_UPLOAD_TYPES,
                accept_multiple_files=True,
                key=f"factual_uploads_{load_ver}",
            )
            if factual_uploads:
                if len(factual_uploads) > MAX_GROUNDING_DOCUMENTS:
                    st.warning(f"Only the first {MAX_GROUNDING_DOCUMENTS} source files will be used.")
                factual_upload_signature = build_upload_signature(factual_uploads)
                if st.session_state.get("factual_upload_signature") != factual_upload_signature:
                    st.session_state["factual_source_catalog"] = extract_cached_grounding_documents(
                        build_file_payloads(factual_uploads),
                        "factual",
                    )
                    st.session_state["factual_upload_signature"] = factual_upload_signature
            elif st.session_state.get("factual_upload_signature"):
                st.session_state["factual_upload_signature"] = ""
                st.session_state["factual_source_catalog"] = []
            render_source_catalog("Source material", st.session_state.get("factual_source_catalog", []))

    task_value = custom_task if task_choice == "Custom task..." else task_choice
    task_ready = bool((task_value or "").strip())
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back to Step 1", use_container_width=True):
            st.session_state["current_step"] = 1
            st.rerun()
    with col2:
        if not task_ready:
            st.caption("Describe the custom task to continue.")
        if st.button("Continue & Finalize →", type="primary", use_container_width=True, disabled=not task_ready):
            st.session_state["current_step"] = 3
            st.rerun()

else:
    render_section_intro(
        "Step 3",
        "Review and generate the prompt package",
        "Confirm the expert framing, grounding, and generation style, then create a package you can review, score, save, and reuse.",
    )
    final_persona = custom_persona_name if "Custom" in persona_choice else persona_choice.split(" ", 1)[-1]
    final_task = custom_task if task_choice == "Custom task..." else task_choice
    style_sources = st.session_state.get("style_source_catalog", [])
    factual_sources = st.session_state.get("factual_source_catalog", [])
    style_brief = build_grounding_brief(st.session_state.get("style_guide_notes", ""), style_sources, "style")
    factual_brief = build_grounding_brief(st.session_state.get("factual_reference_notes", ""), factual_sources, "factual")

    render_mini_cards(
        [
            ("Expert persona", final_persona or "Not specified"),
            ("Task", final_task or "Not specified"),
            ("Generation style", format_generation_mode(st.session_state.get("dspy_mode") and DSPY_AVAILABLE)),
        ]
    )
    render_mini_cards(
        [
            ("Style sources", str(len([s for s in style_sources if not s.get("error")]))),
            ("Factual sources", str(len([s for s in factual_sources if not s.get("error")]))),
            ("Package status", st.session_state.get("approval_status", "draft")),
        ]
    )

    active_model = st.session_state.get("ollama_selected_model", "llama3.1:latest")
    active_base_url = st.session_state.get("ollama_base_url", "http://localhost:11434")
    st.caption(f"Generation will use **{active_model}** at {active_base_url}.")

    inputs_ready = bool((final_persona or "").strip()) and bool((final_task or "").strip())
    gen_label = "Regenerate Package" if st.session_state.get("prompt_package") else "Generate Prompt Package"

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Edit Inputs", use_container_width=True):
            st.session_state["current_step"] = 2
            st.rerun()
    with col2:
        gen_btn = st.button(gen_label, type="primary", use_container_width=True, disabled=not inputs_ready)
    if not inputs_ready:
        st.caption("Persona and task are required before generating. Use **← Edit Inputs** to add them.")

    if gen_btn:
        base_url = st.session_state.get("ollama_base_url", "http://localhost:11434").rstrip("/")
        model_name = st.session_state.get("ollama_selected_model", "llama3.1:latest")
        generator_mode = format_generation_mode(st.session_state.get("dspy_mode") and DSPY_AVAILABLE)
        metadata = prepare_metadata(final_persona, final_task, model_name, base_url, generator_mode, style_sources, factual_sources)
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
        with st.spinner("Generating prompt package..."):
            try:
                if st.session_state.get("dspy_mode") and DSPY_AVAILABLE:
                    method = st.session_state.get("dspy_method", "ChainOfThought")
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
                    package = finalize_prompt_package(
                        package,
                        {**metadata, "dspy_helper_status": helper_status},
                    )
                else:
                    generation_prompt = build_generation_prompt(fallback_package, final_persona, job_role, final_task, additional_context, style_brief, factual_brief)
                    payload = {"model": model_name, "prompt": generation_prompt, "stream": False, "options": {"temperature": 0.2}}
                    response = requests.post(f"{base_url}/api/generate", json=payload, timeout=90)
                    response.raise_for_status()
                    raw_text = response.json().get("response", "")
                    parsed_package, extraction_errors = extract_prompt_package(raw_text)
                    validation_errors = extraction_errors + validate_prompt_package(parsed_package) if parsed_package else extraction_errors
                    if validation_errors:
                        merged_package, repair_notes = merge_prompt_package(parsed_package, fallback_package)
                        merged_errors = validate_prompt_package(merged_package)
                        if not merged_errors:
                            package = finalize_prompt_package(
                                merged_package,
                                {
                                    **metadata,
                                        "generator_mode": "standard (repaired)",
                                    "repair_notes": repair_notes,
                                },
                            )
                            validation_errors = []
                        else:
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
                                package = finalize_prompt_package(
                                    repaired_package,
                                    {
                                        **metadata,
                                        "generator_mode": "standard (second-pass repair)",
                                        "repair_notes": repair_notes + repair_notes_round_2,
                                    },
                                )
                                validation_errors = []
                            else:
                                package = copy.deepcopy(fallback_package)
                                package = finalize_prompt_package(
                                    package,
                                    {
                                        **metadata,
                                        "generator_mode": "fallback after validation issue",
                                        "validation_errors": repaired_errors,
                                        "repair_notes": repair_notes + repair_notes_round_2,
                                    },
                                )
                                validation_errors = repaired_errors
                    else:
                        parsed_package.setdefault("metadata", {})
                        if parsed_package.get("prompt_package_version") != PROMPT_PACKAGE_VERSION:
                            parsed_package["prompt_package_version"] = PROMPT_PACKAGE_VERSION
                        package = finalize_prompt_package(parsed_package, metadata)
                store_package(package, validation_errors)
            except Exception as exc:
                validation_errors = [str(exc)]
                package = copy.deepcopy(fallback_package)
                package = finalize_prompt_package(
                    package,
                    {
                        **metadata,
                        "generator_mode": "fallback after runtime issue",
                        "validation_errors": validation_errors,
                    },
                )
                store_package(package, validation_errors)

    package = st.session_state.get("prompt_package")
    if package:
        validation_errors = st.session_state.get("validation_errors", [])
        if validation_errors:
            st.warning("The model output failed strict validation. A deterministic fallback package was generated instead.")
            for issue in validation_errors:
                st.error(issue)
        else:
            st.success("Prompt package generated and validated successfully.")

        result_action_col1, result_action_col2 = st.columns(2)
        with result_action_col1:
            if st.button("➕ Start New Prompt", use_container_width=True, help="Clear the current inputs and result to build a fresh prompt."):
                reset_for_new_prompt()
                st.rerun()
        with result_action_col2:
            if st.button("← Edit Inputs & Regenerate", use_container_width=True):
                st.session_state["current_step"] = 2
                st.rerun()

        evaluation = package.get("evaluation") or evaluate_prompt_package(package)
        render_score_card(evaluation)

        review_tab, prompt_tab, governance_tab, history_tab = st.tabs(["Overview", "Prompts", "Governance", "History"])

        with review_tab:
            render_mini_cards(
                [
                    ("Package ID", package.get("metadata", {}).get("prompt_package_id", "n/a")),
                    ("Version", str(package.get("metadata", {}).get("version_number", "n/a"))),
                    ("Generation style", package.get("metadata", {}).get("generator_mode", "n/a")),
                ]
            )
            selected_status = st.selectbox("Approval status", ["draft", "approved", "needs_review", "rejected"], index=["draft", "approved", "needs_review", "rejected"].index(st.session_state.get("approval_status", "draft")))
            if selected_status != st.session_state.get("approval_status", "draft"):
                sync_approval_status(selected_status)

            st.markdown("#### Validation checklist")
            score_cols = st.columns(3)
            for index, check in enumerate(evaluation.get("checks", [])):
                with score_cols[index % 3]:
                    if check.get("passed"):
                        st.markdown(f"✅ **{check['label']}**<br/><span style='color:var(--muted-color); font-size:0.85rem'>{check['detail']}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"⚠️ **{check['label']}**<br/><span style='color:var(--warning-color); font-size:0.85rem'>{check['detail']}</span>", unsafe_allow_html=True)

        with prompt_tab:
            st.markdown("**System Prompt**")
            st.code(package.get("system_prompt", ""), language="markdown")
            copy_button_html(
                package.get("system_prompt", ""),
                "Copy System Prompt",
                key="sys_prompt",
                theme_mode=st.session_state.get("theme_mode", "Light"),
            )

            st.markdown("**User Prompt Template**")
            st.code(package.get("user_prompt_template", ""), language="markdown")
            copy_button_html(
                package.get("user_prompt_template", ""),
                "Copy User Prompt",
                key="usr_prompt",
                theme_mode=st.session_state.get("theme_mode", "Light"),
            )

            download_text = f"=== SYSTEM PROMPT ===\n{package.get('system_prompt', '')}\n\n=== USER PROMPT TEMPLATE ===\n{package.get('user_prompt_template', '')}"
            action_col1, action_col2 = st.columns(2)
            with action_col1:
                st.download_button("Download Prompts (.txt)", data=download_text, file_name="generated_prompts.txt", mime="text/plain", use_container_width=True)
            with action_col2:
                st.download_button("Download Prompt Package (.json)", data=json.dumps(package, indent=2), file_name="prompt_package.json", mime="application/json", use_container_width=True)

            if st.button("Save to Prompt Library", use_container_width=True):
                try:
                    saved_entry = save_package_to_library(package)
                    st.session_state["last_saved_library_id"] = saved_entry.get("id")
                    st.success(f"Saved to prompt library as \"{saved_entry.get('title', 'Untitled prompt')}\" (id: {saved_entry.get('id')}).")
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception as exc:  # noqa: BLE001 - surface any storage error to the user
                    st.error(f"Could not save to prompt library: {exc}")

        with governance_tab:
            note_tab, schema_tab = st.tabs(["Analysis & Grounding", "Schemas, Policies & Tests"])
            with note_tab:
                st.info(package.get("persona_analysis", ""))
                st.info(package.get("language_notes", ""))
                st.info(package.get("grounding_strategy", ""))
                repair_notes = package.get("metadata", {}).get("repair_notes", [])
                if repair_notes:
                    st.markdown("**Repair notes**")
                    for note in repair_notes:
                        st.write(f"- {note}")
            with schema_tab:
                st.markdown("**Input schema**")
                st.json(package.get("input_schema", {}))
                st.markdown("**Output schema**")
                st.json(package.get("output_schema", {}))
                st.markdown("**Safety policy**")
                st.json(package.get("safety_policy", {}))
                st.markdown("**Escalation policy**")
                st.json(package.get("escalation_policy", {}))
                st.markdown("**Acceptance tests**")
                st.json(package.get("acceptance_tests", []))
                st.markdown("**Metadata**")
                st.json(package.get("metadata", {}))

        with history_tab:
            history = st.session_state.get("prompt_history", [])
            if not history:
                st.caption("No earlier package versions in this session yet.")
            for index, item in enumerate(reversed(history), start=1):
                metadata = item.get("metadata", {})
                with st.container(border=True):
                    st.markdown(f"**Version {metadata.get('version_number', '?')} • {metadata.get('approval_status', 'draft')}**")
                    st.caption(f"Generated {metadata.get('generated_at', 'n/a')} • Model {metadata.get('model_name', 'n/a')} • {metadata.get('generator_mode', 'n/a')}")
                if st.button("Load this version", key=f"load_history_{index}"):
                    st.session_state["prompt_package"] = copy.deepcopy(item)
                    st.session_state["approval_status"] = item.get("metadata", {}).get("approval_status", "draft")
                    st.rerun()


def render_saved_library_sidebar() -> None:
    """Show prompts saved to the local library, newest first, with their JSON.

    Rendered at the end of the script so a prompt saved during this run (the
    'Save to Prompt Library' button executes earlier) appears immediately.
    """
    with st.sidebar:
        st.markdown("---")
        st.markdown("### Saved to Prompt Library")
        try:
            total = count_library_prompts()
            saved_prompts = list_library_prompts(limit=25)
        except Exception as exc:  # noqa: BLE001 - surface storage/read errors in the UI
            st.caption(f"Could not read the prompt library: {exc}")
            return

        if not saved_prompts:
            st.caption("No prompts saved yet. Generate a package, then use **Save to Prompt Library**.")
            return

        last_saved_id = st.session_state.get("last_saved_library_id")
        suffix = "" if total == 1 else "s"
        more = f" (showing latest {len(saved_prompts)})" if total > len(saved_prompts) else ""
        st.caption(f"{total} saved prompt{suffix}{more}.")

        for entry in saved_prompts:
            is_last = entry.get("id") == last_saved_id
            label = f"{'✅ ' if is_last else ''}{entry.get('title', 'Untitled prompt')}"
            with st.expander(label, expanded=is_last):
                st.json(entry)


render_saved_library_sidebar()
