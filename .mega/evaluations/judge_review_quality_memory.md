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

---

## Iteration 1 — Observations

### What was applied
- **agent.py:234-239 — Severity rubric with behavioral anchors.** Instruction #14 fully rewritten. Blocker = cannot complete core_journey without external help; High = friction directly threatens business_goal; Medium = avoidable effort with no business_goal threat; Nit = polish. Explicit "Do NOT use 'High' as a default; most findings are Medium unless they meet the specific tests below." Nielsen triad (frequency, magnitude, persistence) is required to be reconstructible from impact_on_user + impact_on_business, with a built-in downgrade instruction.
- **agent.py:252-253 — Reflection Loop blocker-cap and downgrade rule.** "At most one Blocker per 5 findings unless the journey is genuinely broken." "If every finding is High, downgrade the weakest." "If the journey works cleanly, it is correct and expected for the review to contain only Medium/Nit — do not invent High/Blocker to add urgency." Plus an explicit triad-reconstruction check.
- **gemini.py — Error classification + exponential backoff.** New exception hierarchy (GeminiPermanentError / GeminiRateLimitError / GeminiTransientError), full-jitter backoff, Retry-After parsing, safety-reason handling via _finish_reason (SAFETY/RECITATION/BLOCKLIST/PROHIBITED_CONTENT → permanent). Out of scope for this judge's criteria — does not address evidence_grounding / persona_voice / validate_review_output.
- **gemini.py — Competitor rule duplicated into plain-text fallback** (gemini.py:309-311). Closes the weakest retry-leakage hole for competitor names. Small evidence_grounding lift.
- **gemini.py — Temperature 0.1, topP 0.95, responseSchema threaded into inline + fallback builders.** Marginal reductions in hallucination variance and score-collapse variance; structural conformance tighter on the weaker builders.

### Effects on criteria
| Criterion | v0 | v1 | Δ | Why |
|-----------|----|----|---|----|
| evidence_grounding | 3.0 | 3.25 | +0.25 | Fallback competitor rule + lower temp + responseSchema threading. No webpage_context post-filter yet. |
| persona_grounding_and_voice | 3.0 | 3.0 | 0 | Not addressed. Voice still surfaces only once at agent.py:191. |
| finding_severity_discipline | 2.0 | 4.0 | +2.0 | Complete Nielsen-triad + behavioral-anchor rewrite. Only headroom is code-level enforcement of the blocker-cap. |
| scoring_rubric_calibration | 2.0 | 2.25 | +0.25 | Lower temperature slightly reduces central-tendency variance. No per-dimension anchors. |
| business_goal_anchoring | 3.5 | 3.5 | 0 | Not addressed. Reinforcement via severity anchor language is incidental. |
| validation_semantic_coverage | 2.0 | 2.0 | 0 | validate_review_output unchanged. Error-classification refactor is infrastructural only. |
| **aggregate** | **2.68** | **3.06** | **+0.38** | |

### New patterns / observations
- The iter-1 gemini.py refactor is well-scoped (HTTP-layer concerns only) and did not bleed into validate_review_output — a clean separation of concerns.
- responseSchema is now applied to `build_request_inline_prompt` and `build_request_plain_text_fallback`, but NOT to `build_request_with_system_instruction` (Gemini bans google_search + responseSchema combination — correctly documented at gemini.py:234). This means the first attempt relies only on prompt-embedded schema + responseMimeType, while the fallback attempts have tighter structural conformance — inverted from intuition but architecturally correct.
- Temperature=0.1 is aggressive for a persona review task; may actually hurt persona voice diversity. Watch for "all reviews sound identical" symptom in next iteration's sample outputs.
- Severity anchor language ("directly threatens the stated business_goal") creates an implicit business_goal-salience boost — small halo effect on business_goal_anchoring that we did not credit numerically (already at 3.5).

### Next iteration (iter 2) — highest ROI
1. **Voice carry-through** (agent.py) — insert voice reminder immediately before `## Execution Instructions` + a voice-audit bullet in Reflection Loop. ~10 lines, lifts persona_grounding_and_voice 3.0 → 4.0.
2. **Thread webpage_context through run_review + evidence substring check + competitor token scan** (service.py + gemini.py). Single structural change. Lifts evidence_grounding 3.25 → 4.0+ AND validation_semantic_coverage 2.0 → 3.0+.
3. **Per-item semantic floor in validate_review_output** (gemini.py) — enforce FINDING_REQUIRED fields are non-empty, priority in enum, journey_stage in JOURNEY_STAGES. Naturally pairs with (2).

If iter 2 lands both (1) and (2+3), aggregate should reach ~3.7–3.8. Target 4.0 then requires iter 3 to add per-dimension scoring anchors (agent.py) and business-goal token-overlap check (gemini.py).

---

## Iteration 2 — Observations

### What was applied
- **agent.py:216-221 — '## Voice Check (do not skip)' block** immediately before '## Execution Instructions'. Names persona.name and persona.voice[:5] as the required anchors and explicitly flags auditor-voice sentences for rewrite. Exactly strategy rq-local-007 step 1.
- **agent.py:261 — Reflection-Loop 'Voice audit' bullet.** Requires re-reading every persona_voice and persona_reason and rewriting any sentence that could plausibly appear in a generic UX audit. Strategy rq-local-007 step 2.
- **gemini.py:77-176 — Two new semantic post-checks.** `_check_evidence_grounding(parsed, webpage_context)` performs a 3-consecutive-word sliding-window match (casefold+whitespace-normalized) over finding.evidence against the crawled page; auto-passes evidence that admits unobservability via _UNOBSERVABLE_PHRASES (`js-rendered`, `javascript`, `dynamic content`, `not observable`, `after login`, …). `_check_competitor_leak(parsed, allowed_competitors, webpage_context)` grep-scans findings+strengths string fields with a grammatical _TITLECASE_MULTIWORD regex (1-5 consecutive Title-case tokens), whitelisting anything in `brief.competitors`, anything word-boundary-present in the crawl, and a curated `_PACKET_SAFELIST` of section headers and enum values (journey stages, scoring dimensions, severity labels, persona field names) so scaffolding text isn't flagged. Both checks auto-disable when both reference sources are empty — pipeline remains usable offline.
- **gemini.py:179-302 — run_review signature + retry loop extended.** Accepts `webpage_context` and `allowed_competitors` kwargs; after structural validate_review_output passes, runs the semantic post-checks; on failure, builds a targeted Retry Note 'Semantic validation failed. Rewrite the review addressing these issues: …' with the top-3 issues. Final attempt bypass at gemini.py:296-297 returns the parsed result rather than starving — defensible tradeoff.
- **service.py:32,50-51 — webpage_context + competitors threaded into run_review.** The v1 memory noted 'webpage_context is dropped after packet assembly'; iter 2 fixes it. `_webpage_context` → `webpage_context`; `allowed_competitors=brief.competitors` added to the run_review call.
- **webapp.py — prefers-reduced-motion CSS fallbacks** (out of scope for review_quality criteria).

### Effects on criteria
| Criterion | v1 | v2 | Δ | Why |
|-----------|----|----|---|----|
| evidence_grounding | 3.25 | 4.25 | +1.00 | Post-filter stack landed: trigram substring check + JS-unobservable escape hatch + grammatical competitor regex + packet safelist + targeted retry hints + final-attempt accept. Belt-and-braces (prompt + code) achieved. Residuals: strengths not scanned, paraphrased evidence can trigram-pass, soft-accept isn't logged. |
| persona_grounding_and_voice | 3.0 | 4.0 | +1.00 | Voice reminder now in the generation-zone (just before Execution Instructions) + Reflection-Loop voice-audit bullet. Residuals: review_summary fields uncovered, no code-level voice probe, fallback persona still has synthetic anchors. |
| finding_severity_discipline | 4.0 | 4.0 | 0 | Unchanged — no diff in severity rubric or blocker-cap. |
| scoring_rubric_calibration | 2.25 | 2.5 | +0.25 | Unaddressed; marginal lift from tightened semantic_issues retry loop reducing score-reason contradiction variance in practice, but no per-dimension or 1/3/5 anchors. Now the top remaining lift. |
| business_goal_anchoring | 3.5 | 3.5 | 0 | Unaddressed. |
| validation_semantic_coverage | 2.0 | 2.75 | +0.75 | validate_review_output itself unchanged (structural-only) BUT the post-check layer now covers the two highest-value semantic gaps (ungrounded evidence, competitor leak) and pipes through targeted retry hints — a big lift for this criterion even though it remains deferred in mid phase. Per-finding field completeness + journey_stage enum + business-goal overlap still missing. |
| **aggregate** | **3.06** | **3.725** | **+0.665** | |

### New patterns / observations
1. **The iter-2 implementation is notably disciplined.** The `_TITLECASE_MULTIWORD` regex + `_PACKET_SAFELIST` pattern avoids the anti-pattern of hardcoding brand names — instead it treats "this is a known Product Name that leaked" as a grammatical shape (multi-word Title Case) constrained by two authorized lists (user-supplied + crawled). This is the right architecture for a pipeline that must work across domains.
2. **Word-boundary padding trick** at gemini.py:205 (`context_padded = f" {context_norm} "`) prevents false-negatives from raw substring containment (e.g. "Stripe" being masked by "restrictions"). Small but shows attention to detail.
3. **JS-unobservable escape hatch** is important for not punishing the model when it correctly admits limitations of the static crawl — a common failure mode in naive grounding checks.
4. **Final-attempt accept** (gemini.py:296-297) is correct architecturally but should emit a soft-warning log so reviewers can audit soft-accept cases. Currently silent.
5. **validate_review_output remains structural-only.** The semantic layer landed in post-checks inside run_review, not in the validator. This creates a subtle split-enforcement — if anyone in the future builds a second caller of validate_review_output thinking it's the full semantic floor, they'll get a false sense of safety.
6. **JOURNEY_STAGES still not enum-enforced in review-output-schema.json** — the memory noted this at iter 0 and 1, and rq-local-005 labels it as trivial effort. Not done yet; still the easiest remaining quick win for validation_semantic_coverage.

### Next iteration (iter 3) — highest ROI
1. **Per-dimension + per-score 1/3/5 anchors** in agent.py `## Scoring Rubric` block — strategy rq-local-002, pure prose, highest single-criterion lift remaining (scoring_rubric_calibration 2.5 → ~3.8).
2. **journey_stage enum in review-output-schema.json** — strategy rq-local-005, trivial (replace bare "string" with pipe-enum), directly lifts validation_semantic_coverage.
3. **Business-goal token-overlap check** in run_review (threading brief.business_goal through like webpage_context was), strategy rq-local-003 partial — cheap code addition, lifts business_goal_anchoring.
4. **Lightweight per-finding field completeness check** in validate_review_output (FINDING_REQUIRED non-empty, priority in enum, journey_stage in JOURNEY_STAGES) to formalize what the post-filter implies and close the split-enforcement risk.

If iter 3 lands (1)+(2)+(3), aggregate should reach ~4.1–4.2 — above the 4.0 target with one iteration to spare for polish (strengths-evidence grounding, voice coverage of review_summary fields, blocker-cap code enforcement).
