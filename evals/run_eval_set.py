from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.package_service import generate_prompt_package

DEFAULT_EVAL_SET_PATH = PROJECT_ROOT / "evals" / "prompt_package_eval_set.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evals" / "results"

PERSONA_NAMES = {
    "doctor": "Healthcare Expert (Doctor/Clinician)",
    "lawyer": "Legal Professional (Attorney/Counsel)",
    "analyst": "Financial Analyst",
    "engineer": "IT Professional (Software Engineer)",
    "researcher": "Researcher",
    "marketer": "Marketing Strategist",
    "hr": "HR Professional",
    "custom": "Custom Professional Expert",
}

GENERATION_STYLE_MAP = {
    "standard": (False, "ChainOfThought"),
    "quality_helper_balanced": (True, "ChainOfThought"),
    "quality_helper_highest": (True, "BestOfN"),
}


def load_eval_set(path: Path | str = DEFAULT_EVAL_SET_PATH) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_source_documents(sources: list[dict[str, Any]], kind: str) -> tuple[list[dict[str, Any]], str]:
    documents: list[dict[str, Any]] = []
    brief_parts: list[str] = []
    for index, source in enumerate(sources or [], start=1):
        source_id = f"SOURCE_{kind.upper()}_{index}"
        name = source.get("name", f"{kind}_{index}")
        purpose = source.get("purpose", "")
        excerpt = source.get("content_excerpt", "")
        summary = f"{purpose}. {excerpt}".strip().strip(".")
        summary = f"{summary}." if summary else ""
        documents.append(
            {
                "source_id": source_id,
                "name": name,
                "summary": summary,
                "text": excerpt,
                "error": None,
                "document_type": source.get("document_type", ""),
                "purpose": purpose,
            }
        )
        if summary:
            brief_parts.append(f"{source_id} ({name}): {summary}")
    return documents, "\n".join(brief_parts).strip()


def scenario_to_request_payload(
    scenario: dict[str, Any],
    *,
    model_name: str,
    base_url: str,
    version_number: int,
    approval_status: str,
) -> dict[str, Any]:
    style_sources, style_brief = build_source_documents(scenario.get("style_sources", []), "style")
    factual_sources, factual_brief = build_source_documents(scenario.get("factual_sources", []), "factual")
    use_quality_helper, quality_method = GENERATION_STYLE_MAP[scenario.get("generation_style", "standard")]
    final_task = scenario.get("custom_task_text") if scenario.get("task") == "Custom task..." else scenario.get("task", "")
    persona_name = scenario.get("persona_name") or PERSONA_NAMES.get(scenario.get("persona_id", "custom"), "Custom Professional Expert")
    return {
        "final_persona": persona_name,
        "job_role": scenario.get("job_role", ""),
        "final_task": final_task or scenario.get("task", ""),
        "additional_context": scenario.get("additional_context", ""),
        "style_brief": style_brief,
        "factual_brief": factual_brief,
        "style_sources": style_sources,
        "factual_sources": factual_sources,
        "model_name": model_name,
        "base_url": base_url,
        "use_quality_helper": use_quality_helper,
        "quality_method": quality_method,
        "version_number": version_number,
        "approval_status": approval_status,
    }


def evaluate_scenario_result(
    scenario: dict[str, Any],
    package: dict[str, Any],
    validation_errors: list[str],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    evaluation = package.get("evaluation") or {}
    checks = evaluation.get("checks", [])
    passed_checks = {check.get("label") for check in checks if check.get("passed")}
    required_checks = set(defaults.get("required_checks", []))
    missing_required_checks = sorted(check for check in required_checks if check not in passed_checks)
    required_placeholders = set(defaults.get("required_placeholders", []))
    user_prompt = str(package.get("user_prompt_template", "") or "")
    placeholders_present = {name for name in required_placeholders if f"[{name}]" in user_prompt}
    missing_placeholders = sorted(required_placeholders - placeholders_present)
    expected_status = defaults.get("expected_status", "draft")
    actual_status = package.get("metadata", {}).get("approval_status", "")
    score_pct = int(evaluation.get("score_pct", 0) or 0)
    score_ok = score_pct >= int(defaults.get("min_score_pct", 0) or 0)
    status_ok = actual_status == expected_status
    validation_ok = not validation_errors
    passed = score_ok and status_ok and validation_ok and not missing_required_checks and not missing_placeholders
    return {
        "scenario_id": scenario.get("id", "unknown"),
        "title": scenario.get("title", "Untitled scenario"),
        "passed": passed,
        "score_pct": score_pct,
        "expected_status": expected_status,
        "actual_status": actual_status,
        "validation_errors": list(validation_errors),
        "missing_required_checks": missing_required_checks,
        "missing_placeholders": missing_placeholders,
        "generator_mode": package.get("metadata", {}).get("generator_mode", "n/a"),
        "package_id": package.get("metadata", {}).get("prompt_package_id", "n/a"),
        "coverage_tags": scenario.get("coverage_tags", []),
    }


def write_csv_report(results: list[dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scenario_id",
        "title",
        "passed",
        "score_pct",
        "expected_status",
        "actual_status",
        "generator_mode",
        "package_id",
        "coverage_tags",
        "missing_required_checks",
        "missing_placeholders",
        "validation_errors",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(
                {
                    **row,
                    "coverage_tags": "; ".join(row.get("coverage_tags", [])),
                    "missing_required_checks": "; ".join(row.get("missing_required_checks", [])),
                    "missing_placeholders": "; ".join(row.get("missing_placeholders", [])),
                    "validation_errors": "; ".join(row.get("validation_errors", [])),
                }
            )


def write_markdown_summary(report: dict[str, Any], summary_path: Path) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {report['title']}",
        "",
        f"Generated at: {report['generated_at']}",
        f"Model: {report['model_name']}",
        f"Base URL: {report['base_url']}",
        "",
        f"Pass rate: **{report['passed_count']}/{report['total_count']}**",
        "",
        "| Scenario | Passed | Score | Generator mode | Notes |",
        "|---|---:|---:|---|---|",
    ]
    for result in report["results"]:
        notes = []
        if result["missing_required_checks"]:
            notes.append(f"Missing checks: {', '.join(result['missing_required_checks'])}")
        if result["missing_placeholders"]:
            notes.append(f"Missing placeholders: {', '.join(result['missing_placeholders'])}")
        if result["validation_errors"]:
            notes.append(f"Validation errors: {', '.join(result['validation_errors'])}")
        note_text = " ; ".join(notes) if notes else "OK"
        lines.append(
            f"| {result['scenario_id']} | {'✅' if result['passed'] else '❌'} | {result['score_pct']}% | {result['generator_mode']} | {note_text} |"
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eval_set(
    *,
    eval_set_path: Path | str = DEFAULT_EVAL_SET_PATH,
    model_name: str = "qwen2.5:latest",
    base_url: str = "http://localhost:11434",
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    eval_set = load_eval_set(eval_set_path)
    defaults = eval_set.get("default_expectations", {})
    results: list[dict[str, Any]] = []
    output_dir = Path(output_dir)

    for index, scenario in enumerate(eval_set.get("scenarios", []), start=1):
        payload = scenario_to_request_payload(
            scenario,
            model_name=model_name,
            base_url=base_url,
            version_number=index,
            approval_status=defaults.get("expected_status", "draft"),
        )
        package, validation_errors = generate_prompt_package(**payload)
        results.append(evaluate_scenario_result(scenario, package, validation_errors, defaults))

    passed_count = sum(1 for result in results if result.get("passed"))
    report = {
        "title": eval_set.get("title", "Prompt Studio eval report"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "base_url": base_url,
        "passed_count": passed_count,
        "total_count": len(results),
        "results": results,
    }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"eval_report_{timestamp}.json"
    csv_path = output_dir / f"eval_report_{timestamp}.csv"
    md_path = output_dir / f"eval_report_{timestamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_csv_report(results, csv_path)
    write_markdown_summary(report, md_path)
    report["output_files"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
    }
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Prompt Studio eval scenarios and export reports.")
    parser.add_argument("--eval-set", default=str(DEFAULT_EVAL_SET_PATH), help="Path to the eval set JSON file.")
    parser.add_argument("--model-name", default="qwen2.5:latest", help="Model name to use for generation.")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Base URL for the underlying generation backend.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for JSON, CSV, and Markdown reports.")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    report = run_eval_set(
        eval_set_path=args.eval_set,
        model_name=args.model_name,
        base_url=args.base_url,
        output_dir=args.output_dir,
    )
    print(json.dumps({
        "passed_count": report["passed_count"],
        "total_count": report["total_count"],
        "output_files": report["output_files"],
    }, indent=2))


if __name__ == "__main__":
    main()
