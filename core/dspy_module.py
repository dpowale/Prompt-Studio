import os
import importlib

try:
    dspy = importlib.import_module("dspy")
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

COMPILED_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "prompt_engineer_compiled_v2.json"
)

if DSPY_AVAILABLE:
    def prompt_quality_metric(example, pred, trace=None):
        """Score a generated prompt pair 0.0–1.0 against structural rules."""
        score = 0
        total = 6
        sp = getattr(pred, "system_prompt", "") or ""
        up = getattr(pred, "user_prompt", "") or ""
        if sp.strip().startswith("You are"):
            score += 1
        if len(sp.split()) >= 80:
            score += 1
        constraint_words = ["never", "always", "must", "do not", "avoid", "flag", "escalate"]
        if any(w in sp.lower() for w in constraint_words):
            score += 1
        if "[" in up and "]" in up:
            score += 1
        structure_words = ["provide:", "(1)", "outline", "list", "summarize", "detail"]
        if any(w in up.lower() for w in structure_words):
            score += 1
        pa = getattr(pred, "persona_analysis", "") or ""
        if len(pa.split()) >= 20:
            score += 1
        return score / total

    DSPY_SEED_EXAMPLES = [
        dspy.Example(
            persona="Physician / Clinician",
            job_role="Neuro-critical care specialist. Manages ICU patients with traumatic brain injury, stroke, and post-operative neurological complications. Applies evidence-based protocols and SOFA scoring.",
            task="Analyze patient admission data and produce a clinical assessment with differential diagnosis",
            context="",
            exemplar_docs="",
            persona_analysis=(
                "A neuro-critical care physician reasons through a strict evidence hierarchy: objective vitals and imaging first, "
                "then lab trends, then clinical gestalt. Communication is precise and structured — SOAP format is the default. "
                "Epistemic standards demand p-values for interventional claims and explicit acknowledgment of diagnostic uncertainty. "
                "Arguments are built deductively from data toward a ranked differential."
            ),
            system_prompt=(
                "You are a Neuro-Critical Care Specialist with attending privileges in a Level I trauma center. "
                "Your clinical reasoning proceeds from objective physiological data — GCS trajectory, ICP trends, lab panels, and neuroimaging — "
                "toward a ranked differential, weighting findings by sensitivity and specificity for the presenting syndrome. "
                "You apply SOFA and APACHE II scoring to stratify severity and guide resource allocation decisions. "
                "Present all assessments in Subjective/Objective/Assessment/Plan format. Use precise medical terminology; "
                "avoid colloquialisms and layman constructions. Behavioral constraints: (1) Always flag jurisdictional variance "
                "in treatment protocols — note when guidelines differ by country or institution. (2) Never prescribe off-label "
                "interventions without explicitly documenting the evidence base and risk-benefit ratio. "
                "(3) Escalate any ambiguous imaging findings to neuroradiology before finalizing the plan."
            ),
            user_prompt=(
                "Analyze the following [CASE_FACTS] for a patient admitted via EMS with a GCS of [GCS_SCORE]. "
                "The patient presents with [PRESENTING_SYMPTOMS]. Review telemetry data including [VITALS_DATA] "
                "and lab results: [LAB_RESULTS]. Provide: (1) a concise assessment of the patient's physiological state "
                "identifying critical trends and deviations, (2) a ranked differential diagnosis with supporting evidence, "
                "(3) immediate interventions and a 24-hour monitoring protocol."
            ),
            language_notes=(
                "GCS score used as a concrete numeric placeholder rather than 'consciousness level' — forces the model to reason "
                "about a specific value. SOFA/APACHE referenced in system prompt to calibrate severity framing. "
                "'Ranked differential' signals evidence-weighted reasoning, not a flat list. "
                "'Flag jurisdictional variance' mirrors real medicolegal communication norms in critical care. "
                "'Escalate to neuroradiology' is standard handoff language in ICU teams."
            ),
            grounding_strategy="No exemplar documents provided.",
        ).with_inputs("persona", "job_role", "task", "context", "exemplar_docs"),

        dspy.Example(
            persona="Attorney / Legal Counsel",
            job_role="Commercial litigation attorney. Advises on contract disputes, regulatory compliance, and M&A due diligence. Jurisdiction: US federal and multi-state.",
            task="Review a contract clause and identify legal risks with recommended mitigation strategies",
            context="",
            exemplar_docs="",
            persona_analysis=(
                "A commercial litigator reads contractual language for ambiguity, enforceability gaps, and jurisdictional exposure. "
                "Reasoning is structured around elements — offer, acceptance, consideration, and damages — then stress-tested against "
                "adverse fact patterns. Communication defaults to hedged precision: claims are qualified by jurisdiction and fact-specificity. "
                "Epistemic standards require citation-level authority before asserting a legal position."
            ),
            system_prompt=(
                "You are a Senior Commercial Litigation Attorney with bar admission in New York, California, and federal courts. "
                "Your legal analysis proceeds element-by-element: you identify ambiguous or unenforceable language, map it to "
                "controlling precedent or statutory authority, and assess exposure under the most adverse plausible fact pattern. "
                "All opinions are jurisdictionally qualified — you note when analysis would differ under UCC Article 2 versus common law, "
                "or across federal circuits. Output contract: structure every response as (1) Issue, (2) Rule, (3) Analysis, (4) Conclusion. "
                "Behavioral constraints: (1) Never assert a definitive legal conclusion without citing authority. "
                "(2) Always flag multi-jurisdictional variance where enforcement outcomes may differ. "
                "(3) Recommend escalation to specialist counsel for IP, tax, or regulatory sub-issues outside commercial litigation scope."
            ),
            user_prompt=(
                "Review the following [CONTRACT_CLAUSE] from a [CONTRACT_TYPE] governed by [GOVERNING_LAW]. "
                "The client's primary concern is [CLIENT_OBJECTIVE]. Provide: (1) identification of ambiguous or unenforceable language "
                "with citation to controlling authority, (2) risk assessment ranked by probability and magnitude of adverse outcome, "
                "(3) three alternative redline formulations that mitigate the identified risks while preserving commercial intent."
            ),
            language_notes=(
                "'Adverse fact pattern' is litigation-authentic framing that signals stress-testing, not neutral reading. "
                "'Jurisdictionally qualified' avoids false universality — critical in multi-state practice. "
                "IRAC structure named explicitly in output contract so the model produces a format attorneys actually use. "
                "'Redline formulations' is the precise term-of-art for contract revision in legal practice. "
                "'Escalation to specialist counsel' mirrors professional responsibility obligations under Model Rules."
            ),
            grounding_strategy="No exemplar documents provided.",
        ).with_inputs("persona", "job_role", "task", "context", "exemplar_docs"),
    ]

    class GenerateExpertPromptPair(dspy.Signature):
        """Generate a high-quality system prompt and user prompt for a professional persona.
        Use domain-authentic language. System prompt opens with 'You are [title]' and defines
        reasoning posture, role scope, accepted data sources, grounding and citation behavior,
        uncertainty handling, behavioral constraints, and escalation triggers (120-250 words).
        User prompt is a concrete structured request with [PLACEHOLDER_NAME] slots (80-160 words),
        an inline output contract, source attribution instructions, and explicit direction not to
        invent facts or hide uncertainty. If exemplar_docs are provided, calibrate vocabulary,
        tone, and terminology to them without copying the reference text verbatim."""

        persona: str = dspy.InputField(desc="Professional persona title and type")
        job_role: str = dspy.InputField(desc="Detailed role responsibilities and domain context")
        task: str = dspy.InputField(desc="Specific task the AI must accomplish")
        context: str = dspy.InputField(desc="Additional constraints or background (may be empty)", default="")
        exemplar_docs: str = dspy.InputField(desc="Reference documents to ground vocabulary and tone (may be empty)", default="")

        persona_analysis: str = dspy.OutputField(
            desc="3-4 sentences: how this professional reasons, communicates, structures arguments, and what epistemic standards they apply"
        )
        system_prompt: str = dspy.OutputField(
            desc="System prompt 120-250 words. Opens with 'You are [specific title]'. Defines role scope, accepted data sources, grounding/citation behavior, uncertainty posture, output contract, and 2-3 behavioral constraints. Integrated prose, not a bullet list."
        )
        user_prompt: str = dspy.OutputField(
            desc="User prompt 80-160 words. Concrete structured request with semantically named [PLACEHOLDER_NAME] slots. Specifies desired output structure inline, requires source attribution when facts are grounded, and tells the downstream model to label uncertainty and escalate when out of scope. Domain-authentic phrasing."
        )
        language_notes: str = dspy.OutputField(
            desc="5-7 specific domain vocabulary choices, register decisions, or rhetorical moves and why each was chosen"
        )
        grounding_strategy: str = dspy.OutputField(
            desc="How exemplar documents shaped vocabulary, framing, structure, or tone. Write 'No exemplar documents provided' if none given."
        )

    class PromptEngineerModule(dspy.Module):
        """DSPy module with ChainOfThought + manual quality validation and retry."""
        def __init__(self):
            self.generate = dspy.ChainOfThought(GenerateExpertPromptPair)

        def _violations(self, pred):
            issues = []
            sp = pred.system_prompt or ""
            up = pred.user_prompt or ""
            if not sp.strip().startswith("You are"):
                issues.append("System prompt MUST open with 'You are [specific professional title]'.")
            if len(sp.split()) < 80:
                issues.append("System prompt is too short — expand to 120+ words covering reasoning posture, output contract, and behavioral constraints.")
            if "source" not in sp.lower() and "cite" not in sp.lower():
                issues.append("System prompt MUST define source attribution or citation behavior when factual grounding is available.")
            if "uncert" not in sp.lower() and "insufficient" not in sp.lower():
                issues.append("System prompt MUST explain how to handle uncertainty or insufficient evidence.")
            if "[" not in up or "]" not in up:
                issues.append("User prompt MUST contain at least one semantically named [PLACEHOLDER_NAME] slot.")
            if not any(w in up.lower() for w in ["provide:", "(1)", "outline", "summarize", "detail", "list"]):
                issues.append("User prompt MUST specify a desired output structure inline (e.g. 'Provide: (1)..., (2)..., (3)...').")
            if "source" not in up.lower() and "[source" not in up.lower():
                issues.append("User prompt MUST mention source attribution when using grounded facts.")
            return issues

        def forward(self, persona, job_role, task, context="", exemplar_docs=""):
            pred = self.generate(
                persona=persona,
                job_role=job_role,
                task=task,
                context=context,
                exemplar_docs=exemplar_docs,
            )
            for _ in range(2):
                issues = self._violations(pred)
                if not issues:
                    break
                correction_hint = " ".join(issues)
                pred = self.generate(
                    persona=persona,
                    job_role=job_role,
                    task=task,
                    context=f"{context}\n\nCORRECTION REQUIRED: {correction_hint}".strip(),
                    exemplar_docs=exemplar_docs,
                )
            return pred

    class BestOfNModule(dspy.Module):
        """Generates N candidates at varied temperatures, scores each, returns best and all candidates."""

        TEMPERATURES = [0.0, 0.35, 0.65]

        def __init__(self):
            self.generate = dspy.ChainOfThought(GenerateExpertPromptPair)

        def run_all(
            self,
            lm_factory,
            persona, job_role, task, context="", exemplar_docs=""
        ):
            candidates = []
            for i, temp in enumerate(self.TEMPERATURES):
                lm = lm_factory(temp)
                with dspy.context(lm=lm):
                    pred = self.generate(
                        persona=persona,
                        job_role=job_role,
                        task=task,
                        context=context or "",
                        exemplar_docs=exemplar_docs or "",
                    )
                score = prompt_quality_metric(None, pred)
                checks = [
                    {"label": "Opens 'You are'",         "passed": (pred.system_prompt or "").strip().startswith("You are")},
                    {"label": "System ≥80 words",         "passed": len((pred.system_prompt or "").split()) >= 80},
                    {"label": "Constraint language",      "passed": any(w in (pred.system_prompt or "").lower() for w in ["never","always","must","do not","avoid","flag","escalate"])},
                    {"label": "[PLACEHOLDER] in user",    "passed": "[" in (pred.user_prompt or "") and "]" in (pred.user_prompt or "")},
                    {"label": "Output structure inline",  "passed": any(w in (pred.user_prompt or "").lower() for w in ["provide:","(1)","outline","list","summarize","detail"])},
                    {"label": "Persona analysis ≥20 words","passed": len((pred.persona_analysis or "").split()) >= 20},
                ]
                candidates.append({
                    "candidate": i + 1,
                    "temperature": temp,
                    "score": score,
                    "score_pct": int(score * 100),
                    "checks": checks,
                    "pred": pred,
                    "system_prompt_preview": (pred.system_prompt or "")[:160].strip() + "…",
                    "user_prompt_preview":   (pred.user_prompt   or "")[:100].strip() + "…",
                })
            candidates.sort(key=lambda x: x["score"], reverse=True)
            for rank, c in enumerate(candidates, 1):
                c["rank"] = rank
            return candidates[0]["pred"], candidates

    def _load_or_build_module():
        """Return a compiled PromptEngineerModule (from disk if available, else bootstrap)."""
        module = PromptEngineerModule()
        if os.path.exists(COMPILED_MODULE_PATH):
            try:
                module.load(COMPILED_MODULE_PATH)
                return module, "loaded"
            except Exception:
                pass
        return module, "uncompiled"

    def compile_dspy_module(lm):
        """Run BootstrapFewShot compilation and save to disk. Returns compiled module."""
        with dspy.context(lm=lm):
            optimizer = dspy.BootstrapFewShot(
                metric=prompt_quality_metric,
                max_bootstrapped_demos=2,
                max_labeled_demos=2,
            )
            compiled = optimizer.compile(PromptEngineerModule(), trainset=DSPY_SEED_EXAMPLES)
        compiled.save(COMPILED_MODULE_PATH)
        return compiled
