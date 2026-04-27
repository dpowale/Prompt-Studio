import copy
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
from core.utils import evaluate_prompt_package, extract_prompt_package, finalize_prompt_package, merge_prompt_package, validate_prompt_package
from ui.components import copy_button_html
from ui.theme import THEME_PRESETS, theme_css

if DSPY_AVAILABLE:
    from core.dspy_module import COMPILED_MODULE_PATH, BestOfNModule, _load_or_build_module, compile_dspy_module


st.set_page_config(page_title="Prompt Studio", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

PERSONAS = {
    "⚕️ Healthcare Expert (Doctor/Clinician)": ("doctor", "Healthcare"),
    "⚖️ Legal Professional (Attorney/Counsel)": ("lawyer", "Legal"),
    "📊 Financial Analyst": ("analyst", "Finance"),
    "💻 IT Professional (Software Engineer)": ("engineer", "Technology"),
    "🔬 Researcher": ("researcher", "Research"),
    "📣 Marketing Strategist": ("marketer", "Marketing"),
    "🤝 HR Professional": ("hr", "Human Resources"),
    "✏️ Write Your Own (Custom)": ("custom", "Custom"),
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
        "approval_status": "draft",
        "load_ver": 0,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


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
1. `system_prompt` must start with "You are" and cover role scope, accepted data sources, grounding rules, uncertainty handling, compliance constraints, refusal triggers, red-team checks, and escalation triggers.
2. `user_prompt_template` must include semantically named placeholders such as [TASK_GOAL], [INPUT_CONTENT], [CONSTRAINTS], [OUTPUT_AUDIENCE], [DELIVERABLE_FORMAT], [STYLE_GUIDE], [FACTUAL_SOURCES], and [FACT_SOURCE_1] where relevant.
3. When factual grounding is present, require inline source attribution using [SOURCE_ID] tokens and separate verified facts from assumptions.
4. Keep `input_schema`, `output_schema`, `safety_policy`, `escalation_policy`, `acceptance_tests`, and `metadata` as JSON objects or arrays, not strings.
5. Never fabricate citations, policies, legal conclusions, medical advice, financial claims, or customer-specific facts.
6. The package must be safe for commercial use and auditable by a human reviewer.
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
5. Ensure `system_prompt` starts with `You are` and remains at least 120 words.
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


def build_api_request_example(package: dict) -> dict:
    metadata = package.get("metadata", {})
    style_source_count = int(metadata.get("style_source_count", 0) or 0)
    factual_source_count = int(metadata.get("factual_source_count", 0) or 0)
    return {
        "persona": metadata.get("persona", "Custom Persona"),
        "job_role": package.get("persona_analysis", ""),
        "task": metadata.get("task", "Custom task"),
        "additional_context": "",
        "style_brief": package.get("grounding_strategy", ""),
        "factual_brief": package.get("grounding_strategy", ""),
        "style_sources": [{"name": f"style_source_{idx + 1}.txt"} for idx in range(style_source_count)],
        "factual_sources": [{"name": f"factual_source_{idx + 1}.txt"} for idx in range(factual_source_count)],
        "model_name": metadata.get("model_name", st.session_state.get("ollama_selected_model", "llama3.1:latest")),
        "base_url": metadata.get("ollama_base_url", st.session_state.get("ollama_base_url", "http://localhost:11434")),
        "use_quality_helper": package.get("metadata", {}).get("settings", {}).get("quality_helper_enabled", False),
        "quality_method": "BestOfN" if package.get("metadata", {}).get("settings", {}).get("quality_mode") == "highest" else "ChainOfThought",
    }


def build_api_snippets(package: dict) -> tuple[str, str, str]:
    request_payload = build_api_request_example(package)
    request_json = json.dumps(request_payload, indent=2)
    curl_snippet = (
        'curl -X POST "http://127.0.0.1:8000/generate-package" '
        '-H "Content-Type: application/json" '
        f"-d '{json.dumps(request_payload)}'"
    )
    python_snippet = f"""import requests\n\npayload = {request_json}\nresponse = requests.post(\"http://127.0.0.1:8000/generate-package\", json=payload, timeout=120)\nresponse.raise_for_status()\npackage = response.json()[\"package\"]\npackage"""
    server_snippet = "uvicorn api_server:app --host 127.0.0.1 --port 8000"
    return server_snippet, curl_snippet, python_snippet


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


def render_hero_section() -> None:
        st.markdown(
                """
                <div class='hero-shell'>
                    <div class='hero-eyebrow'>Prompt Studio</div>
                    <div class='hero-title'>Turn expert knowledge to AI prompts</div>
                    <div class='hero-subtitle'>Turn expert tasks into structured prompts with validation, grounding, and reusable package history — all from one guided workflow.</div>
                    <div class='chip-row'>
                        <span class='chip'>✦ Runs locally</span>
                        <span class='chip'>✓ Quality-checked prompts</span>
                        <span class='chip'>🗂️ Style + Grounding references</span>
                        <span class='chip'>💾 Save and reuse prompts</span>
                    </div>
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
                st.markdown(f"**{value}**")


def render_score_card(evaluation: dict) -> None:
    passed = int(evaluation.get("passed", 0) or 0)
    total = int(evaluation.get("total", 0) or 0)
    score_pct = int(evaluation.get("score_pct", 0) or 0)
    with st.container(border=True):
        left_col, right_col = st.columns([4, 1])
        with left_col:
            st.markdown("### 📊 Readiness score")
            st.caption(f"Passed {passed}/{total} validation checks across structure, grounding, and safety.")
        with right_col:
            st.metric("Score", f"{score_pct}%")
        st.progress(max(0, min(score_pct, 100)) / 100)


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
    with st.expander("⚙️ Advanced AI Options", expanded=False):
        ollama_base_url = st.text_input("Ollama URL (Local AI Engine)", value=st.session_state.get("ollama_base_url", "http://localhost:11434"))
        st.session_state["ollama_base_url"] = ollama_base_url.rstrip("/")

        try:
            ollama_models = fetch_ollama_models(st.session_state["ollama_base_url"])
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
            st.session_state["dspy_mode"] = st.toggle("Use DSPy to improve prompt writing (optional)", value=st.session_state.get("dspy_mode", False))
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
    st.download_button("💾 Save Project", data=json.dumps(state_to_save, indent=2), file_name="prompt_builder_save.json", mime="application/json", use_container_width=True)

    uploaded_state = st.file_uploader("📂 Load Project", type=["json"], label_visibility="collapsed")
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

    st.markdown("---")
    with st.expander("Notebook / API integration", expanded=False):
        package_for_api = st.session_state.get("prompt_package")
        if package_for_api:
            server_snippet, curl_snippet, python_snippet = build_api_snippets(package_for_api)
            st.caption("Start the local API server, then call it from a notebook, script, or another app.")
            st.markdown("**Start local API server**")
            st.code(server_snippet, language="bash")
            st.markdown("**cURL example**")
            st.code(curl_snippet, language="bash")
            st.markdown("**Python / notebook example**")
            st.code(python_snippet, language="python")
        else:
            st.caption("Generate or load a prompt package to see notebook and API snippets here.")

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
    if st.button("Continue to Step 2 →", type="primary", use_container_width=True):
        st.session_state["current_step"] = 2
        st.rerun()

elif current_step == 2:
    render_section_intro(
        "Step 2",
        "Define the task and grounding inputs",
        "Give the app the task, any constraints, and optional references so the final prompt package is easier to control and review.",
    )
    safe_task_index = TASKS.index(task_choice) if task_choice in TASKS else len(TASKS) - 1
    task_choice = st.selectbox("Select a typical task:", TASKS, index=safe_task_index, key=f"task_choice_{load_ver}")
    st.session_state["task_choice"] = task_choice
    if task_choice == "Custom task...":
        custom_task = st.text_input("Describe the task here:", value=custom_task, placeholder="Example: Draft a customer-ready incident response summary.", key=f"custom_task_{load_ver}")
        st.session_state["custom_task"] = custom_task

    additional_context = st.text_area("Business rules, formatting needs, or constraints", value=additional_context, height=90, placeholder="Example: Keep it under 250 words, cite the policy source, and flag unresolved risks.", key=f"additional_context_{load_ver}")
    st.session_state["additional_context"] = additional_context

    st.write("---")
    st.markdown("### Style grounding")
    render_helper_card(
        "Use style references for tone and structure",
        f"Upload up to {MAX_GROUNDING_DOCUMENTS} files to guide voice, heading patterns, vocabulary, and formatting. These references shape style only, not factual claims.",
    )
    style_guide_notes = st.text_area("Manual style guidance", value=style_guide_notes, height=110, placeholder="Example: Sound like a concise enterprise policy memo. Prefer short paragraphs and plain language.", key=f"style_notes_{load_ver}")
    st.session_state["style_guide_notes"] = style_guide_notes
    style_uploads = st.file_uploader("Upload style references", type=SUPPORTED_UPLOAD_TYPES, accept_multiple_files=True, key=f"style_uploads_{load_ver}")
    if style_uploads:
        if len(style_uploads) > MAX_GROUNDING_DOCUMENTS:
            st.warning(f"Only the first {MAX_GROUNDING_DOCUMENTS} style documents will be used.")
        st.session_state["style_source_catalog"] = extract_grounding_documents(style_uploads, "style")
    render_source_catalog("Uploaded style references", st.session_state.get("style_source_catalog", []))

    st.write("---")
    st.markdown("### Factual grounding")
    render_helper_card(
        "Use factual references for evidence only",
        f"Upload up to {MAX_GROUNDING_DOCUMENTS} files that contain approved facts. The generated package will require source attribution and should separate evidence from assumptions.",
    )
    factual_reference_notes = st.text_area("Manual factual notes", value=factual_reference_notes, height=110, placeholder="Example: Internal policy summary, approved pricing language, or customer requirements.", key=f"factual_notes_{load_ver}")
    st.session_state["factual_reference_notes"] = factual_reference_notes
    factual_uploads = st.file_uploader("Upload factual references", type=SUPPORTED_UPLOAD_TYPES, accept_multiple_files=True, key=f"factual_uploads_{load_ver}")
    if factual_uploads:
        if len(factual_uploads) > MAX_GROUNDING_DOCUMENTS:
            st.warning(f"Only the first {MAX_GROUNDING_DOCUMENTS} factual documents will be used.")
        st.session_state["factual_source_catalog"] = extract_grounding_documents(factual_uploads, "factual")
    render_source_catalog("Uploaded factual references", st.session_state.get("factual_source_catalog", []))

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back to Step 1", use_container_width=True):
            st.session_state["current_step"] = 1
            st.rerun()
    with col2:
        if st.button("Continue & Finalize →", type="primary", use_container_width=True):
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

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Edit Inputs", use_container_width=True):
            st.session_state["current_step"] = 2
            st.rerun()
    with col2:
        gen_btn = st.button("✨ Generate Prompt Package", type="primary", use_container_width=True)

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
                        {
                            **metadata,
                            "dspy_helper_status": helper_status,
                        },
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
            copy_button_html(package.get("system_prompt", ""), "Copy System Prompt", key="sys_prompt")

            st.markdown("**User Prompt Template**")
            st.code(package.get("user_prompt_template", ""), language="markdown")
            copy_button_html(package.get("user_prompt_template", ""), "Copy User Prompt", key="usr_prompt")

            download_text = f"=== SYSTEM PROMPT ===\n{package.get('system_prompt', '')}\n\n=== USER PROMPT TEMPLATE ===\n{package.get('user_prompt_template', '')}"
            action_col1, action_col2 = st.columns(2)
            with action_col1:
                st.download_button("📥 Download Prompts (.txt)", data=download_text, file_name="generated_prompts.txt", mime="text/plain", use_container_width=True)
            with action_col2:
                st.download_button("🧾 Download Prompt Package (.json)", data=json.dumps(package, indent=2), file_name="prompt_package.json", mime="application/json", use_container_width=True)

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
