# Prompt Studio

Prompt Studio is a local prompt-building app that helps users create clear, structured, and reusable AI prompt packages. Instead of only generating a basic prompt, it produces a full package with system instructions, user prompt templates, safety rules, input/output structure, and review metadata. It is designed for folks who want more reliable and organized prompt workflows without deep prompt-engineering experience.

Built with Streamlit and Ollama, Prompt Studio keeps generation local and privacy-friendly. Users can choose an expert role, describe a task, add style or factual reference documents, and generate prompts that are easier to review, reuse, and improve over time. It also includes optional quality-enhancement with DSPy, prompt history, approval status tracking, and local API support for notebooks or automation.

The package includes:

- `system_prompt`
- `user_prompt_template`
- `input_schema`
- `output_schema`
- `safety_policy`
- `escalation_policy`
- `acceptance_tests`
- `metadata`
- `evaluation`

Prompt history, approval tracking, and project-level audit context are managed by the app and included in project export rather than stored as fields inside every single package.

---

## Current Features

- Persona-driven prompt package generation
- Optional DSPy-enhanced generation
- Reusable LLM helpers for local Ollama and external provider integrations
- Strict JSON package validation before display or save
- Deterministic fallback package when model output fails validation
- Separate **style grounding** and **factual grounding** inputs
- Real file upload support for `.txt`, `.md`, `.pdf`, and `.docx`
- Chunking and lightweight summarization of uploaded grounding documents
- Source-attribution rules for factual grounding
- Readiness scoring with saved evaluation results
- Prompt package history, versioning, and approval status
- JSON project export and import
- Reusable prompt library for saved system/user prompts, exposed via REST API and an MCP server

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.10+ | |
| Streamlit | 1.35+ | UI |
| requests | 2.31+ | Ollama API |
| pypdf | recent | PDF grounding extraction |
| python-docx | recent | DOCX grounding extraction |
| dspy-ai | optional | DSPy generation mode |
| mcp | recent | Prompt-library MCP server (`mcp_server.py`) |
| Ollama | recent | Local model runtime |

---

## Quick Start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Make sure Ollama is running and at least one model is installed:

```bash
ollama list
```

3. Start the app:

```bash
streamlit run prompt_studio.py --server.port 8515
```

4. Open `http://localhost:8515`

---

## Workflow

### Step 1 — Persona
Choose a professional persona or define a custom one.

### Step 2 — Task and grounding
Provide:

- task description
- business rules or constraints
- optional style guidance
- optional factual reference notes
- optional uploaded style documents
- optional uploaded factual documents

### Step 3 — Generate
The app builds a validated prompt package and stores:

- the full package JSON
- evaluation checks and score
- package version number
- model and settings metadata
- approval status
- prompt history

### Prompt package status

Each generated package includes a prompt package status stored as `approval_status`.

Available values in the UI:

- `draft`
- `approved`
- `needs_review`
- `rejected`

Where status is stored:

- current session state for the active package
- `metadata.approval_status` inside each prompt package
- prompt package history for prior versions
- exported project JSON when you use Save Project

Status persistence behavior:

- status is kept in Streamlit session state while the app is open
- status is not auto-saved to a database or separate file
- status is restored when you load a previously exported project JSON

---

## Grounding Model

Prompt Studio separates grounding into two lanes:

### Style grounding
Used to influence:

- tone
- phrasing
- structure
- vocabulary density
- brand-safe formatting

### Factual grounding
Used only for:

- evidence-backed statements
- factual claims
- cited assertions
- downstream source attribution

When factual grounding is present, generated prompts require the downstream model to cite facts using `[SOURCE_ID]` labels.

---

## Validation and Safety

Before a package is shown or saved, Prompt Studio validates that it includes:

- a versioned package schema
- a `system_prompt` that starts with `You are`
- a structured `user_prompt_template` with semantic placeholders
- `input_schema` and `output_schema`
- `safety_policy` with privacy, evidence, and refusal controls
- `escalation_policy` for out-of-scope or high-risk requests
- acceptance tests
- audit metadata

If direct model output fails validation, the app does **not** silently accept it. It records the validation failure and generates a deterministic fallback package instead.

---

## DSPy Mode

DSPy mode is optional.

For most users, DSPy is simply an **extra quality mode**.

When you turn it on, Prompt Studio takes an extra pass at writing the prompt package so the wording is often clearer, more structured, and more consistent.

### When to use it

Use DSPy when you want:

- stronger prompt wording
- more consistent structure
- better results for harder tasks

Leave it off when you want:

- faster generation
- the simplest setup
- fewer dependencies

### DSPy choices in the app

- **Balanced quality (faster)** — a good default for most users
- **Highest quality (slower)** — tries more than one option and keeps the best result

### Training behavior

On the first DSPy run, Prompt Studio automatically trains the DSPy helper if it does not already exist.

This saves stronger example patterns so later DSPy runs can reuse them.

The saved DSPy helper is stored as `prompt_engineer_compiled_v2.json` in the project root.

- it is a generated helper artifact, not a user prompt package
- it can be deleted safely
- if deleted, Prompt Studio will recreate it automatically the next time DSPy runs

The app still includes a **Train DSPy helper** button if you want to retrain it manually later.

DSPy does not replace validation. Prompt Studio still checks the generated package, keeps metadata and scoring local, and falls back safely if needed.

---

## Project Structure

```text
Prompt Studio/
├── api_server.py
├── mcp_server.py
├── core/
│   ├── dspy_module.py
│   ├── fallback_builder.py
│   ├── grounding.py
│   ├── llm_api.py
│   ├── package_service.py
│   ├── prompt_library.py
│   └── utils.py
├── ui/
│   ├── components.py
│   └── theme.py
├── prompt_studio.py
├── requirements.txt
└── README.md
```

---

## LLM API Helpers

The shared helpers in [core/llm_api.py](core/llm_api.py) now support both local and external model integrations.

Available helpers:

- `fetch_ollama_models(base_url)` — list models from a local Ollama server
- `call_external_llm_api(...)` — send a prompt to a supported external provider and return text output
- `fetch_external_models(...)` — list models from a supported external provider when a `/models` endpoint is available

Supported external provider styles:

- `openai-compatible` — endpoints that expose `/chat/completions`
- `anthropic` — endpoints that expose `/messages`

Supported options include:

- `base_url`
- `model_name`
- `api_key`
- optional `system_prompt`
- `temperature`
- `max_tokens`
- custom headers and extra payload fields

These helpers are intended for integration work in services, scripts, or future UI/API extensions. The main app still uses Ollama directly unless additional provider wiring is added.

---

## Programmatic Use

Prompt generation runs **in-process**, not behind an HTTP service. To generate prompt packages from a notebook, script, or automation tool, import the package service directly:

```python
from core.package_service import generate_prompt_package

package, validation_errors = generate_prompt_package(
    final_persona="Marketing Strategist",
    job_role="Owns launch messaging and campaign planning.",
    final_task="Draft professional emails or letters",
    additional_context="Keep the output concise and easy to review.",
    style_brief="Use short paragraphs and clear headings.",
    factual_brief="Use only approved product facts.",
    model_name="qwen2.5:latest",
    base_url="http://localhost:11434",
)
```

The bundled eval runner (`evals/run_eval_set.py`) uses this same in-process path for batch generation.

The HTTP API service (`api_server.py`) is **library-only** — it stores and retrieves saved prompts. See [Prompt Library (API + MCP)](#prompt-library-api--mcp) below.

---

## Prompt Library (API + MCP)

Generated system and user prompts can be saved to a reusable **prompt library** so they can be retrieved later from the app, scripts, or AI tooling. The library is a single local JSON file (`prompt_library.json` by default) written atomically, and the **same store** is exposed two ways: a REST API service and an MCP server.

Set the library location with the `PROMPT_LIBRARY_PATH` environment variable (defaults to `prompt_library.json` in the project root).

Each stored entry includes `id`, `title`, `persona`, `task`, `system_prompt`, `user_prompt`, `tags`, `approval_status`, `model_name`, `source_package_id`, a content hash (used for de-duplication), timestamps, and a `metadata` block.

The `persona` and `task` values are automatically added to `tags` (de-duplicated against any tags you pass), so prompts are filterable by persona or task via the `tag` query filter.

### Saving from the app

After generating a package, click **Save to Prompt Library** in the prompt tab. Saving the same prompt content twice returns the existing entry instead of creating a duplicate.

### REST API service

The library endpoints are served by the same FastAPI app (`api_server.py`):

```bash
uvicorn api_server:app --host 127.0.0.1 --port 8000
```

- `POST /library/prompts` — save a `system_prompt` / `user_prompt` pair with optional `title`, `persona`, `task`, `tags`, `approval_status`, `model_name`, `source_package_id`, `metadata`, `dedupe`
- `POST /library/save-package` — save the system/user prompt extracted from a full generated `package`
- `GET /library/prompts` — list prompts, with optional `persona`, `task`, `tag`, `search`, and `limit` query filters (newest first)
- `GET /library/prompts/{id}` — fetch one prompt
- `DELETE /library/prompts/{id}` — delete one prompt

`GET /health` also reports the active `library_path` and `library_count`.

### MCP server

`mcp_server.py` exposes the library to MCP clients (such as Claude Desktop) over stdio:

```bash
python mcp_server.py
```

Tools: `save_prompt`, `list_prompts`, `get_prompt`, `delete_prompt`.

Example MCP client registration:

```json
{
  "mcpServers": {
    "prompt-studio-library": {
      "command": "python",
      "args": ["mcp_server.py"],
      "env": { "PROMPT_LIBRARY_PATH": "prompt_library.json" }
    }
  }
}
```

The MCP SDK (`mcp`) is listed in `requirements.txt`. The Streamlit app and REST API do not require it; only the MCP server does.

---

## Evaluation Set and Reports

Prompt Studio includes a reusable evaluation set in [evals/prompt_package_eval_set.json](evals/prompt_package_eval_set.json).

It covers:

- all built-in personas
- all task types in the app
- all grounding modes
- all supported document types: `.txt`, `.md`, `.pdf`, `.docx`
- standard and quality-helper generation styles
- common risk patterns such as missing evidence, conflicting sources, regulated content, privacy-sensitive input, and out-of-scope requests

You can run the evaluation set and export reports with:

```bash
python evals/run_eval_set.py
```

Optional arguments:

- `--model-name`
- `--base-url`
- `--eval-set`
- `--output-dir`

The runner exports:

- JSON report
- CSV report
- Markdown summary report

By default, reports are written under `evals/results/`.

---

## Notes

- The app currently focuses on **single-model generation with auditability**, not side-by-side comparison.
- Uploaded files are summarized for grounding and stored in exported project state.
- Approval state and prompt history are session-managed, stored in package metadata, and included in project export.

---

## License

MIT
