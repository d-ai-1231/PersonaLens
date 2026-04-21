# Judge: Review Output Quality — Cumulative Memory

## File Map (baseline — iteration 0)

Maps each part of the review contract to its implementing file:

- `src/personalens/agent.py`
  - `SYSTEM_PROMPT` (lines 11-54): persona voice, evidence discipline, JS-dynamic warning, competitor rule, "FUNDAMENTAL EVALUATION FRAMEWORK" for business-goal anchoring.
  - `VALIDATION_CRITERIA` (lines 57-65): self-check checklist injected into Reflection Loop.
  - `JOURNEY_STAGES` (lines 68-76): 7 allowed values — NOT currently enum-enforced in the response schema (schema treats journey_stage as any string).
  - `SCORING_DIMENSIONS` (lines 79-88): 8 bare dimension names; no per-dimension definitions, no behavioral anchors per score level.
  - `build_response_json_schema` / `_schema_from_template` (lines 102-145): converts the schema template to a strict JSON schema. `int == 1` in the template becomes `{integer, minimum:1, maximum:5}`; pipe-delimited strings become enums; additionalProperties:false.
  - `build_review_packet` (lines 148-261): assembles packet markdown including Execution Instructions (lines 217-237) and Reflection Loop (lines 240-247). Voice anchors are surfaced at line 191 but not reinforced near the Execution Instructions / Reflection Loop.

- `src/personalens/gemini.py`
  - `GeminiConfig` (lines 15-20): default model `gemini-2.5-pro`.
  - `run_review` (lines 23-78): iterates 3 request builders x 2 retries each. Retry notes are generic (empty-response / invalid-JSON / "structurally empty").
  - `validate_review_output` (lines 115-123): THIN — checks only that four top-level keys are non-empty and at least one of strengths/findings is populated. Per-item semantic completeness not checked.
  - `build_request_with_system_instruction` (139-168): uses systemInstruction, enables google_search grounding.
  - `build_request_inline_prompt` (171-192): no systemInstruction, no search. Rule-carrying text is inside the packet only.
  - `build_request_plain_text_fallback` (195-212): no systemInstruction, no search, just "return JSON". **Weakest competitor-rule defense** — relies entirely on packet text.
  - `enrich_persona` (222-328): Two-stage persona generation with web-search grounding + fallback. Triangulates user description + web research + site snapshot. Strong prompt discipline (lines 252-257 forbid competitor names in persona fields).

- `src/personalens/models.py`
  - `ReviewBrief.validate` (70-115): enforces >=1 goal, >=1 pain_point, >=3 voice anchors, >=1 evidence_source, confidence in {low,medium,high}, device_context in {mobile,desktop,mixed}. This is the ONLY semantic floor for the persona.

- `review-output-schema.json`: output contract.
  - `scores.*` uses integer literal 1 — expands to {min:1,max:5} via _schema_from_template.
  - `priority` uses "Blocker|High|Medium|Nit" pipe syntax — expands to strict enum.
  - `technical_level`, `confidence`, `device_context`, `estimated_effort` — pipe-enums.
  - `journey_stage` is bare "string" — NOT enum-enforced despite JOURNEY_STAGES being defined.
  - Every finding requires: priority, title, journey_stage, problem, persona_voice, evidence, impact_on_user, impact_on_business, improvement_direction. Every prioritized_improvements.quick_wins/structural_fixes entry requires: change, expected_user_outcome, expected_business_outcome, estimated_effort.

- `src/personalens/markdown_report.py`: passive renderer — will propagate any garbage through to the user. No filtering.

- `src/personalens/service.py` (119-134): fallback persona used when Gemini enrichment fails. Generic voice defaults ("practical, time-conscious, skeptical, low-hype") — risk of synthetic-persona theater if the fallback ships.

## Recurring Patterns / Observations

1. **Prompt-only guardrails.** Every rule (competitor rule, JS-dynamic warning, business-goal anchoring, evidence discipline) lives in prose inside SYSTEM_PROMPT or Execution Instructions. No post-response code-level enforcement.
2. **Competitor rule is repeated 3x** in the packet (SYSTEM_PROMPT line 46, Execution Instructions implicitly, "## Known Competitors" header line 195) — but survives only in the first request builder. The plain-text fallback strips systemInstruction entirely, making it the weakest link for rule leakage.
3. **Retry loop wastes information.** run_review retries are generous (3 builders x 2) but the previous_failure text is generic ("invalid JSON", "structurally empty") — the model never gets semantic feedback like "finding #2 cites evidence not present in the crawl".
4. **webpage_context is dropped after packet assembly.** build_packet_for_brief (service.py:20) returns it alongside the packet, but run_review_for_brief (service.py:23-53) discards it — so post-response evidence checks against the crawl cannot happen without threading it through.
5. **Journey stage duplication.** JOURNEY_STAGES is listed in the packet as a constraint, but the response schema accepts any string for journey_stage. Easy fix: use pipe-enum in review-output-schema.json.
6. **Score template trick.** Setting an int field to `1` in review-output-schema.json triggers the special case in _schema_from_template (agent.py:130-132) that generates `{min:1,max:5}`. This is clever but undocumented — any future editor who changes `1` to another int will silently drop the range.

## Baseline Gap Analysis (by criterion)

| Criterion | Baseline | Biggest gap | Cheapest lift |
|-----------|----------|-------------|---------------|
| evidence_grounding | 3.0 | No post-response filter for competitors/evidence | Thread webpage_context into run_review + add substring check + competitor-token check |
| persona_grounding_and_voice | 3.0 | Voice not reinforced after the persona card is listed | Add voice anchors + persona_voice instruction near Execution Instructions + Reflection Loop |
| finding_severity_discipline | 2.0 | No behavioral anchors for Blocker|High|Medium|Nit | Add Nielsen-triad anchors in the Execution Instructions |
| scoring_rubric_calibration | 2.0 | No per-dimension or per-score anchors | Add a "## Scoring Rubric" block with 1-line description per dimension + anchor for score 1/3/5 |
| business_goal_anchoring | 3.5 | No textual-overlap check between expected_business_outcome and brief.business_goal | Simple tokenizer-overlap check in validate_review_output |
| validation_semantic_coverage | 2.0 | validate_review_output checks only top-level non-emptiness | Expand validator to per-item field completeness + journey_stage enum + persona_voice non-empty |

## Target for Iteration Budget

- Baseline aggregate: 2.68
- Target: 4.0
- Reachable in 5 iterations if fixes are prioritized: severity + scoring anchors (prompt-only, single file) first, then the semantic post-filter + validator (gemini.py + agent.py), then voice-carry-through polish.

## What To Focus On Next Iteration (iter 1)

Active criteria this phase (early): evidence_grounding, persona_grounding_and_voice, finding_severity_discipline.

Highest-ROI fixes:
1. **Severity anchors** in agent.py Execution Instructions — directly lifts finding_severity_discipline and reduces Blocker inflation that would otherwise propagate into prioritized_improvements.
2. **Voice reinforcement** in agent.py build_review_packet — cheap prose addition near Execution Instructions + Reflection Loop; exploits already-required voice anchors.
3. **Competitor-name post-filter + evidence substring check** in gemini.py run_review — one structural change that lifts evidence_grounding meaningfully; requires threading webpage_context through run_review_for_brief in service.py.

Deferred until mid/late phase: per-score behavioral anchors, validate_review_output expansion, business-goal textual-overlap check.
