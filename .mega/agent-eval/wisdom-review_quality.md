# Wisdom Cheatmap — Review Output Quality
## Session: review_quality | Event: optimize/step4/curate

> **Source**: Local fallback — PCR endpoint unavailable (404). Synthesized from
> `judge_review_quality_memory.md` baseline analysis + local wisdom store.
> Criteria baseline: 2.68 → target 4.0.

---

## Strategy 1: Behavioral Anchors for Severity Rating Scale
<!-- wisdom_id: rq-local-001 -->

**Symptom addressed**: No behavioral anchors for Blocker/High/Medium/Nit — central-inflation risk (all findings become High, Blocker never used or overused).

**Fix**: Add a `## Severity Definitions` block to the Execution Instructions section of `build_review_packet` in `agent.py`. Each level must carry a one-line definition and a concrete disqualifying example:

```
## Severity Definitions

- **Blocker**: Stops the user from completing their primary goal entirely.
  Example: "Checkout CTA is hidden below the fold on mobile — user cannot proceed."
  NOT a Blocker: slow load time, minor label copy.

- **High**: Causes measurable user failure or significant drop-off in a primary flow.
  Example: "Form error is shown but field is not highlighted — users give up."
  NOT High: cosmetic inconsistency, nice-to-have feature.

- **Medium**: Creates friction but user can recover with extra effort.
  Example: "Filter state resets on page reload — user must re-apply."
  NOT Medium: minor wording preference, color contrast <3:1 only on decorative element.

- **Nit**: Polish-level issue with negligible user impact.
  Example: "Icon alignment off by 2px at 1440px breakpoint."
  NOT a Nit: any issue that causes a user to abandon a task.
```

Place this block immediately before the `## Execution Instructions` line so it is in scope when the model generates each finding's `priority` field.

**Why it works**: Explicit disqualifying examples ("NOT a Blocker") are the most effective calibration mechanism for LLM severity assignment. Without them the model defaults to social desirability — escalating to High/Blocker to appear thorough. The disqualifiers create a semantic fence that forces demotion.

**Criteria lifted**: `finding_severity_discipline` (2.0 → 3.5 estimated), `scoring_rubric_calibration` (secondary).

---

## Strategy 2: Per-Score Rubric Anchors for Scoring Dimensions
<!-- wisdom_id: rq-local-002 -->

**Symptom addressed**: `SCORING_DIMENSIONS` lists 8 bare dimension names with no per-dimension definition and no anchor for what score 1 / 3 / 5 means — central-tendency collapse produces five near-identical 3/5 scores.

**Fix**: Add a `## Scoring Rubric` block to `build_review_packet` (agent.py), placed after the persona card and before the main evaluation section. For each dimension, provide:

1. A one-line definition of what the dimension measures.
2. A 1-line anchor for score 1 (failing), 3 (adequate), and 5 (excellent).

Minimal template (expand per dimension):

```
## Scoring Rubric

| Dimension | Measures | Score 1 | Score 3 | Score 5 |
|-----------|----------|---------|---------|---------|
| usability | Ease of task completion for this persona | User cannot complete any primary task | User completes tasks with notable friction | User completes all primary tasks without hesitation |
| visual_design | Visual hierarchy, consistency, brand alignment | Broken layout or severe inconsistency | Consistent but generic; hierarchy unclear in some areas | Strong hierarchy, brand-coherent, no visual noise |
| performance | Perceived speed and responsiveness from persona's device | Visible jank/blocking; user abandons | Acceptable speed with minor lag spikes | Instant-feeling; no perceptible delay |
| accessibility | WCAG compliance and inclusive design signals | Multiple barriers for common assistive needs | Partial compliance; some barriers remain | Full perceivable/operable/understandable compliance |
| content_quality | Clarity, terminology match to persona's mental model | Jargon-heavy or misleading copy | Clear but some terminology mismatch | Copy precisely matches persona's language and expectations |
| mobile_experience | Touch targets, layout reflow, mobile-specific flows | Broken or unusable on persona's primary device | Functional but not optimized for mobile | Optimized layout, thumb-zone targets, no desktop spillover |
| trust_signals | Presence and credibility of social proof, security cues | Absent or counterproductive trust cues | Some cues present but weak or inconsistent | Compelling, persona-relevant trust signals throughout |
| conversion_flow | CTA clarity and friction in goal-completion paths | CTA absent or misleading; flow broken | CTA present; minor friction in checkout/signup path | Low-friction, clear CTA hierarchy, no dead ends |
```

In `build_response_json_schema` / `review-output-schema.json`, add a `reason` string field to each score object (already hinted in prompt_pipeline cheatmap — `{reason, score}` ordering activates chain-of-thought before committing a number).

**Why it works**: Central-tendency collapse is caused by under-specification. When the model has no anchor for what distinguishes a 3 from a 5, it defaults to 3 to hedge. Explicit 1/3/5 anchors shift the decision from "what feels right" to "which row matches the evidence I just cited."

**Criteria lifted**: `scoring_rubric_calibration` (2.0 → 3.8 estimated), `evidence_grounding` (forces reason-before-score discipline).

---

## Strategy 3: Semantic Validator Expansion Beyond Structural Checks
<!-- wisdom_id: rq-local-003 -->

**Symptom addressed**: `validate_review_output` in `gemini.py` (lines 115-123) checks only top-level key presence and non-emptiness. A stub finding with `priority="High"`, `title="Issue"`, and no `evidence`, `persona_voice`, or `journey_stage` passes validation. Semantic completeness is not checked.

**Fix**: Replace the stub validator with a per-item semantic floor check in `gemini.py`:

```python
def validate_review_output(data: dict) -> tuple[bool, str]:
    # --- Structural check (existing) ---
    required_top = {"scores", "findings", "prioritized_improvements", "executive_summary"}
    if not required_top.issubset(data):
        return False, f"Missing top-level keys: {required_top - data.keys()}"
    if not data.get("findings") and not data.get("scores"):
        return False, "Both findings and scores are empty"

    # --- Journey stage enum check ---
    from personalens.agent import JOURNEY_STAGES
    valid_stages = set(JOURNEY_STAGES)
    for i, finding in enumerate(data.get("findings", [])):
        stage = finding.get("journey_stage", "")
        if stage not in valid_stages:
            return False, f"finding[{i}].journey_stage '{stage}' not in JOURNEY_STAGES"

    # --- Per-finding semantic floor ---
    FINDING_REQUIRED = {"priority", "title", "journey_stage", "problem",
                        "persona_voice", "evidence", "impact_on_user",
                        "impact_on_business", "improvement_direction"}
    PRIORITY_ENUM = {"Blocker", "High", "Medium", "Nit"}

    for i, finding in enumerate(data.get("findings", [])):
        missing = FINDING_REQUIRED - finding.keys()
        if missing:
            return False, f"finding[{i}] missing fields: {missing}"
        if not str(finding.get("evidence", "")).strip():
            return False, f"finding[{i}] has empty evidence — hallucination risk"
        if not str(finding.get("persona_voice", "")).strip():
            return False, f"finding[{i}] has empty persona_voice"
        if finding.get("priority") not in PRIORITY_ENUM:
            return False, f"finding[{i}].priority '{finding.get('priority')}' not in enum"

    # --- Business goal overlap check (tokenizer-based) ---
    business_goal_tokens = set(
        data.get("_brief_business_goal", "").lower().split()
    ) - {"the", "a", "an", "to", "and", "or", "of", "in", "for"}
    for qi in data.get("prioritized_improvements", {}).get("quick_wins", []):
        outcome = qi.get("expected_business_outcome", "")
        overlap = business_goal_tokens & set(outcome.lower().split())
        if business_goal_tokens and not overlap:
            return False, f"quick_win expected_business_outcome has no overlap with brief.business_goal"

    return True, "ok"
```

Thread `brief.business_goal` into the output dict as `_brief_business_goal` before calling `validate_review_output` (strip it before returning to the caller). This enables the token-overlap check without schema changes.

**Why it works**: The structural stub allowed semantically hollow findings to pass. Per-item field completeness + empty-string checks block the most common hallucination pattern (field present but empty). The business-goal token-overlap check catches "generic outcome" anti-patterns that sound plausible but don't reference the brief.

**Criteria lifted**: `validation_semantic_coverage` (2.0 → 3.5 estimated), `evidence_grounding` (empty-evidence block), `business_goal_anchoring`.

---

## Strategy 4: Evidence Substring Check via Threaded webpage_context
<!-- wisdom_id: rq-local-004 -->

**Symptom addressed**: `webpage_context` is assembled in `build_packet_for_brief` (service.py:20) alongside the packet but is discarded by `run_review_for_brief` (service.py:23-53). No post-response check verifies that `finding.evidence` strings are grounded in the actual crawl.

**Fix**:

**Step 1 — Thread webpage_context through run_review** (service.py):

```python
# service.py — run_review_for_brief
packet, webpage_context = build_packet_for_brief(brief, persona)
review_data = run_review(packet, webpage_context=webpage_context)  # ADD kwarg
```

**Step 2 — Add evidence grounding check in run_review** (gemini.py):

```python
def run_review(packet: str, webpage_context: str = "") -> dict:
    ...
    # After successful parse and validate_review_output:
    if webpage_context:
        failed = _check_evidence_grounding(review_data, webpage_context)
        if failed:
            # Use failed list as semantic retry hint
            retry_hint = f"EVIDENCE NOT GROUNDED: {failed}. Revise these findings to cite text visible in the webpage."
            # Re-run with hint injected into next attempt's failure context
            ...
    return review_data

def _check_evidence_grounding(data: dict, context: str) -> list[str]:
    """Return list of finding titles whose evidence cites no substring from context."""
    context_lower = context.lower()
    failed = []
    for f in data.get("findings", []):
        evidence = f.get("evidence", "")
        # Extract quoted phrases or key nouns from evidence (simple heuristic)
        # Treat any 4-word window as a candidate anchor
        words = evidence.lower().split()
        anchored = any(
            " ".join(words[i:i+3]) in context_lower
            for i in range(len(words) - 2)
        ) if len(words) >= 3 else bool(evidence.strip())
        if not anchored:
            failed.append(f.get("title", f"finding[{data['findings'].index(f)}]"))
    return failed
```

**Step 3 — Competitor-name post-filter** (gemini.py, same pass):

```python
def _check_competitor_leak(data: dict, competitor_names: list[str]) -> list[str]:
    """Return any competitor names found in any string field of the output."""
    import json
    text = json.dumps(data).lower()
    return [c for c in competitor_names if c.lower() in text]
```

Call `_check_competitor_leak` before returning; if non-empty, trigger a semantic retry with `"COMPETITOR LEAK: {names}. Remove all competitor references and rephrase findings."`.

**Why it works**: Without grounding checks, the model can hallucinate evidence ("The CTA button text says 'Sign Up Now'" when the crawl shows a different label). A 3-gram window check is lightweight and catches the most common hallucination pattern. Competitor-name checks are string-match — near-zero cost.

**Criteria lifted**: `evidence_grounding` (3.0 → 4.0 estimated), `validation_semantic_coverage` (secondary).

---

## Strategy 5: Journey Stage Enum Enforcement in Response Schema
<!-- wisdom_id: rq-local-005 -->

**Symptom addressed**: `JOURNEY_STAGES` (7 allowed values, agent.py lines 68-76) is listed in the packet as a prose constraint, but `review-output-schema.json` specifies `journey_stage` as bare `"string"`. Any string passes — values like `"onboarding"`, `"checkout"`, `"unknown"` silently pollute the output.

**Fix**: In `review-output-schema.json`, change the `journey_stage` field to use the pipe-enum syntax already supported by `_schema_from_template`:

```json
"journey_stage": "Awareness|Consideration|Onboarding|Core Usage|Retention|Support|Offboarding"
```

`_schema_from_template` in `agent.py` (lines 102-145) will expand this to `{"type": "string", "enum": [...]}` automatically — no code changes required. This is the same mechanism used for `priority`, `technical_level`, `confidence`, `device_context`, and `estimated_effort`.

Also add `journey_stage` to the `JOURNEY_STAGES` definition as the canonical source and derive the schema string from it programmatically to keep them in sync:

```python
# agent.py
JOURNEY_STAGES = ["Awareness", "Consideration", "Onboarding", "Core Usage", "Retention", "Support", "Offboarding"]
JOURNEY_STAGE_SCHEMA_VALUE = "|".join(JOURNEY_STAGES)  # used in schema template
```

**Why it works**: Schema-enforced enums are enforced at Gemini's constrained-decoding layer — the model cannot emit an invalid value regardless of what it "wants" to write. Prose-only constraints rely on instruction-following, which degrades under high-complexity prompts and on fallback request builders that strip `systemInstruction`.

**Criteria lifted**: `validation_semantic_coverage` (direct fix), `evidence_grounding` (stage-mismatch is a form of grounding error).

---

## Strategy 6: Competitor-Name Post-Filter in run_review
<!-- wisdom_id: rq-local-006 -->

**Symptom addressed**: The competitor rule is stated 3× in the packet and once in `SYSTEM_PROMPT`, but `build_request_plain_text_fallback` (gemini.py lines 195-212) drops `systemInstruction` entirely. At the weakest retry, only the packet text carries the rule — and the packet's `## Known Competitors` header (line 195 of agent.py) can itself be a training signal that activates competitor-name recall.

**Fix**: Add a post-response string-scan pass (see Strategy 4 Step 3 for implementation). Extract the known-competitors list from the packet or from a module-level constant:

```python
# agent.py — add alongside JOURNEY_STAGES
KNOWN_COMPETITORS: list[str] = []  # populated at packet-build time from brief.known_competitors

# gemini.py run_review — after any successful parse:
leaks = _check_competitor_leak(review_data, known_competitors)
if leaks:
    raise SemanticValidationError(f"Competitor names in output: {leaks}")
    # or: trigger semantic retry with the hint
```

Additionally, strengthen the plain-text fallback (`build_request_plain_text_fallback`) by injecting the competitor rule explicitly into its prompt body even without `systemInstruction`:

```python
# gemini.py build_request_plain_text_fallback
COMPETITOR_RULE = (
    "CRITICAL RULE: Do not name, reference, or compare to any competitor product "
    "or service. All findings must describe this product only."
)
prompt = f"{COMPETITOR_RULE}\n\n{packet}\n\nReturn valid JSON only."
```

**Why it works**: The plain-text fallback is the defense's weakest link. Adding the rule explicitly to its prompt body closes the gap without requiring structural changes. The post-response scan is a deterministic backstop that catches any leak regardless of which builder produced the response.

**Criteria lifted**: `evidence_grounding` (competitor leak = anti-grounding), `validation_semantic_coverage`.

---

## Strategy 7: Voice Carry-Through Reinforcement Near Execution Instructions
<!-- wisdom_id: rq-local-007 -->

**Symptom addressed**: Voice anchors are surfaced at `agent.py` line 191 (inside the persona card block) but are not referenced again near the `## Execution Instructions` or `## Reflection Loop` — the sections where findings and `persona_voice` fields are actually generated.

**Fix**: In `build_review_packet` (agent.py), add a one-line voice reminder immediately before the `## Execution Instructions` header:

```python
voice_reminder = (
    f"\n> **Voice check**: Every `persona_voice` field must echo the anchors: "
    f"{', '.join(persona.voice_anchors[:3])}. "
    f"Write in first person as {persona.name}.\n"
)
packet += voice_reminder
packet += "\n## Execution Instructions\n"
```

Also add to the `## Reflection Loop` prompt (agent.py lines 240-247) a single voice-audit bullet:

```
- Voice audit: For each finding, does `persona_voice` sound like {persona.name} using the defined anchors? If not, rewrite before proceeding.
```

**Why it works**: LLMs have finite effective context windows for instruction-following. A voice anchor mentioned 200 tokens before the generation zone has significantly stronger influence than one mentioned 1,500 tokens earlier in the persona card. The Reflection Loop bullet catches any persona_voice drift before the response is finalized.

**Criteria lifted**: `persona_grounding_and_voice` (3.0 → 4.0 estimated).

---

## Strategy 8: Semantic Retry Feedback with Finding-Level Diagnostics
<!-- wisdom_id: rq-local-008 -->

**Symptom addressed**: `run_review` in `gemini.py` retries with generic failure text ("invalid JSON", "structurally empty", "validation failed"). The model receives no semantic signal about *which* findings failed or *why* — it cannot improve specific outputs across retries.

**Fix**: Pass structured failure context into each retry attempt's prompt. After any `validate_review_output` failure or semantic check failure (evidence grounding, competitor leak, empty persona_voice), build a diagnostic string:

```python
def _build_retry_hint(validation_error: str, failed_findings: list[str] = None) -> str:
    hint = f"PREVIOUS ATTEMPT FAILED: {validation_error}\n"
    if failed_findings:
        hint += "FINDINGS REQUIRING REVISION:\n"
        for title in failed_findings:
            hint += f"  - {title}: evidence not grounded in the crawl or persona_voice empty\n"
    hint += "\nFix only the listed issues. Do not change findings that passed validation."
    return hint
```

Inject this into the user-turn content of the next retry attempt:

```python
# gemini.py run_review retry loop
if attempt > 0:
    retry_context = _build_retry_hint(last_error, last_failed_findings)
    packet_with_context = f"{retry_context}\n\n---\n\n{packet}"
else:
    packet_with_context = packet
```

**Why it works**: Generic retry prompts force the model to re-generate the entire response from scratch with no guidance — it has equal probability of repeating the same error. Finding-level diagnostics constrain the repair scope: the model is told exactly which items failed and why, dramatically increasing the probability that the next attempt fixes those items while preserving valid content.

**Criteria lifted**: `evidence_grounding` (retry path now has semantic signal), `validation_semantic_coverage`, `persona_grounding_and_voice`.

---

## Implementation Priority

| Strategy | Criteria | Est. Lift | Effort | Do First |
|---|---|---|---|---|
| 1 — Severity Anchors | finding_severity_discipline | +1.5 | Low (prose in agent.py) | Yes |
| 2 — Score Rubric Anchors | scoring_rubric_calibration | +1.8 | Low (prose + schema field) | Yes |
| 5 — Journey Stage Enum | validation_semantic_coverage | +0.5 | Trivial (schema string) | Yes |
| 3 — Semantic Validator | validation_semantic_coverage | +1.5 | Medium (gemini.py) | Early |
| 4 — Evidence Substring | evidence_grounding | +1.0 | Medium (service.py + gemini.py) | Early |
| 6 — Competitor Post-Filter | evidence_grounding | +0.5 | Low (gemini.py) | Early |
| 7 — Voice Carry-Through | persona_grounding_and_voice | +1.0 | Low (agent.py) | Early |
| 8 — Semantic Retry Feedback | all semantic criteria | +0.3 | Medium (gemini.py) | Mid |

**Recommended iteration sequence**:
- Iteration 1: Strategies 1, 2, 5, 7 (prompt-only + trivial schema, single file `agent.py`)
- Iteration 2: Strategies 3, 6 (gemini.py validator + competitor filter)
- Iteration 3: Strategy 4 (thread webpage_context, evidence grounding)
- Iteration 4: Strategy 8 (semantic retry diagnostics)
