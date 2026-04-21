# judge_prompt_pipeline — cumulative memory

## Code Map (as of iter 0)

### Primary prompt & LLM files
- `src/personalens/gemini.py`
  - `GeminiConfig` (line 15-20): `model="gemini-2.5-pro"`, `timeout_seconds=45`. No temperature, no topP, no responseSchema field.
  - `run_review` (line 23-78): 3 builders × 2 attempts = up to 6 calls. Unconditional retry loop, no sleep, no jitter. Injects `previous_failure` into retry prompt (correct behavior).
  - `_make_request` (line 81-102): urllib-based, swallows HTTP status classification into blanket `GeminiError`.
  - `validate_review_output` (line 115-123): only checks top-level non-empty sections; minimal.
  - `build_request_with_system_instruction` (line 139-168): has systemInstruction, google_search tool, responseMimeType only.
  - `build_request_inline_prompt` (line 171-192): no systemInstruction, no tools, responseMimeType only.
  - `build_request_plain_text_fallback` (line 195-212): no responseMimeType — REGRESSION path, not true fallback.
  - `enrich_persona` (line 222-328): ~85-line prompt. 2-attempt fallback (grounded → plain). Blanket `except (GeminiError, json.JSONDecodeError)`.

- `src/personalens/agent.py`
  - `SYSTEM_PROMPT` (line 11-54): well-structured role + framework; contains competitor rule (lines 46-52) and EVALUATE-not-EXPAND framework (lines 23-37).
  - `build_response_json_schema` (line 102-118): computes a proper JSON Schema from the template with `propertyOrdering`. COMPUTED BUT NEVER SENT to the API.
  - `build_review_packet` (line 148-261): assembles markdown packet. Embeds SYSTEM_PROMPT into markdown (line 169-170). Embeds full schema as JSON code block at end (line 250-253). Has another competitor-rule restatement in the "Known Competitors" section header (line 195). Execution instructions items 7-10 (line 227-230) restate EVALUATE-not-EXPAND. Reflection loop (line 244-246) restates it a third time.

- `review-output-schema.json`
  - scores fields ordered `{score, reason}` (lines 24-31) — reasoning-BEFORE-commit is violated.

- `src/personalens/service.py`
  - `build_packet_for_brief` (line 17-20): calls `fetch_webpage_context` once per review.
  - `generate_persona_from_form` (line 84-135): calls `fetch_webpage_context` AGAIN for persona enrichment. DUPLICATE FETCH per end-to-end request.
  - Hardcoded `"gemini-2.5-pro"` default in 3 function signatures (lines 17, 84, 138).

- `src/personalens/webpage.py`
  - `MAX_PAGES=8`, `MAX_EXCERPT_CHARS=2200` (line 14-15). ~4.4k tokens per crawl output, no relevance filter.

## Recurring Patterns (baseline)
- **Schema-in-prompt duplication**: schema object is built correctly but never attached; instead embedded as markdown JSON.
- **Competitor rule restated 3x** (SYSTEM_PROMPT + packet header + enrich_persona prompt).
- **EVALUATE-not-EXPAND restated 3x** (SYSTEM_PROMPT + exec instructions + reflection loop).
- **No temperature setting** anywhere — uses Gemini 2.5 Pro's ~1.0 default, wrong for JSON.
- **No retry backoff / no jitter / no error classification** — 6 retries fire instantly regardless of error type.
- **Duplicate webpage fetch** per end-to-end request (persona stage + review stage).
- **3 divergent builder shapes** — retries change prompt structure, making debugging harder.
- **3rd fallback builder drops responseMimeType** — a quality regression, not a fallback.

## Baseline Scores (iter 0)
- prompt_quality: 2.5
- llm_configuration: 1.5
- retry_reliability: 1.5
- pipeline_structure: 2.0
- token_efficiency: 2.5
- aggregate: 2.0
- target: 4.0

---

## Iter 1 Observations & Results (phase: mid)

### What got fixed (verified against diff + current source)
1. **Retry reliability overhaul (gemini.py:17-30, 48-59, 62-66, 82-147, 165-175)** — three-class error hierarchy (GeminiPermanentError / GeminiRateLimitError / GeminiTransientError), full-jitter exponential backoff capped at 30s, 3 max attempts, Retry-After honored on 429, SAFETY/RECITATION/BLOCKLIST/PROHIBITED_CONTENT finishReason treated as permanent. enrich_persona uses same classification (lines 432-444). RESULT: retry_reliability 1.5 → 4.5.
2. **Temperature + top_p set (gemini.py:44-45, 214-220)** — GeminiConfig now has temperature=0.1, top_p=0.95; _base_generation_config applies them to all 3 builders + both enrich_persona bodies. Fixes the Gemini-2.5-pro default-1.0 problem for JSON tasks.
3. **responseSchema partially wired (gemini.py:268-269, 300-301)** — builders 2 (inline) and 3 (plain-text fallback) now attach responseSchema; the grounded builder intentionally omits it because google_search + responseSchema is incompatible on Gemini (correct call). Plain-text fallback also regained responseMimeType, fixing the regression.
4. **Severity rubric added (agent.py:234-239, 252-253)** — behavioral anchors for Blocker/High/Medium/Nit + Nielsen triad (frequency/magnitude/persistence) self-check in reflection loop. Real quality content, modest token cost (~200).

### What was NOT addressed in iter 1
- Schema still embedded in packet markdown (agent.py:258-260) AND attached as responseSchema — the explicit "defense in depth" choice contradicts Google's controlled-generation guidance and blocks higher scores on both llm_configuration and token_efficiency.
- Competitor rule now in 4 locations (SYSTEM_PROMPT, packet header, plain-text fallback builder, enrich_persona prompt) — iter 1 added a copy rather than consolidating.
- EVALUATE-not-EXPAND still 3×.
- SYSTEM_PROMPT still duplicated in systemInstruction AND packet markdown — prefix stability/caching still poor.
- review-output-schema.json scores still {score, reason} — reasoning-before-commit still violated.
- Duplicate fetch_webpage_context across persona + review stages — unchanged.
- No persona cache.
- Both stages hardcoded gemini-2.5-pro, no flash tier for persona.
- 3 divergent builder shapes retained rather than consolidated.

### Iter 1 Scores
- prompt_quality: 2.75 (+0.25 from severity rubric)
- llm_configuration: 3.5 (+2.0 from temperature + partial responseSchema)
- retry_reliability: 4.5 (+3.0 — major win)
- pipeline_structure: 2.5 (+0.5 from partial schema attachment)
- token_efficiency: 2.5 (unchanged — schema duplication erased what could have been a big win)
- aggregate: 3.26 (+1.26)

### Lessons Learned
- Retry-classification work was the biggest single-lift reward (+3.0 on a critical criterion).
- "Defense in depth" schema duplication is tempting but actively wrong per Google docs — a single-attachment strategy with a short schema reminder in prompt is better.
- Severity rubric design (behavioral anchors + Nielsen triad) is a model-quality improvement that's worth its token cost. Good pattern to keep.

## What to Focus On Next Iteration (iter 2, phase: mid)

Active criteria: prompt_quality, llm_configuration, retry_reliability, pipeline_structure. (token_efficiency becomes active in late phase — iter ≥ 4.)

Highest-leverage single change remaining: **DELETE the embedded schema JSON block from build_review_packet (agent.py:257-260)**. Replace with a one-line reference to the top-level keys. This reclaims ~500-800 tokens/call, removes the anti-pattern Google explicitly warns against, and can lift llm_configuration to ~4.0-4.5.

Second: **fix duplicate fetch_webpage_context** — add `@functools.lru_cache` to webpage.py or thread the context through service.py so persona + review share one crawl. +0.5-1.0 on pipeline_structure.

Third: **consolidate competitor rule** to SYSTEM_PROMPT only (delete 3 restatements). Reorder review-output-schema.json scores to {reason, score}. +0.5-1.0 on prompt_quality.

Fourth (polish): Retry-After HTTP-date form support; decouple builder-switch from API-layer attempt index. +0.25 on retry_reliability.

Watch for: when schema is removed from prompt, confirm all 3 builders still produce valid JSON (builder 1 must work without responseSchema since google_search blocks it — rely on responseMimeType + short key list). If builder 1 starts failing more often, consider dropping google_search from the default retry path and using it only as a tool the model can invoke explicitly.

---

## Iter 2 Observations & Results (phase: mid)

### What got fixed in iter 2
1. **Post-response semantic validation added (gemini.py:70-203, 281-302)** — two new validators run AFTER parse/structural validation:
   - `_check_evidence_grounding`: scans findings[].evidence, passes if any 3-word window appears in webpage_context (normalized) OR the evidence admits it's not observable (JS-rendered/dynamic/behind login). Gracefully disables when webpage_context is missing.
   - `_check_competitor_leak`: scans findings/strengths for multi-word title-cased tokens not in allowed_competitors and not in webpage_context. Packet-scaffolding safelist (section headers, enum values) prevents false positives from quoted structure. Gracefully disables when both references empty.
   - Semantic failures are injected into next retry's Retry Note — correct validation-failure-retry pattern.
   - Last-attempt bypass (gemini.py:296-297) accepts rather than starving the loop when a term genuinely can't be anchored.
   - RESULT: retry_reliability 4.5 → 4.75.
2. **webpage_context + allowed_competitors threaded through service.py (service.py:32, 45-52)** — previously `_webpage_context` was discarded; now feeds the semantic validators. Makes iter 2's Gemini-side validation actually functional.
3. **Voice Check section + voice audit reflection bullet (agent.py:216-222, 261)** — adds explicit persona-voice audit instruction. Real quality content at ~6 lines prompt cost. prompt_quality 2.75 → 3.0.

### What was NOT addressed in iter 2 (all iter 1 priority_fixes carry forward)
- Schema still embedded in packet markdown (agent.py:266-268) AND attached as responseSchema.
- review-output-schema.json still `{score, reason}` order (lines 24-31) — reasoning-before-commit still violated.
- Duplicate fetch_webpage_context across persona (service.py:90) + review (service.py:18) stages — unchanged.
- No persona cache by (service, type, description) hash.
- Both stages hardcoded gemini-2.5-pro (service.py:17, 86, 140).
- SYSTEM_PROMPT still duplicated in systemInstruction AND packet markdown.
- Competitor rule now in 4 locations (SYSTEM_PROMPT + Known Competitors header + plain-text fallback + enrich_persona).
- 3 divergent builder shapes still retained.
- EVALUATE-not-EXPAND still 3×.

### Iter 2 Scores
- prompt_quality: 3.0 (+0.25 from Voice Check)
- llm_configuration: 3.5 (unchanged)
- retry_reliability: 4.75 (+0.25 from semantic validation layer)
- pipeline_structure: 3.0 (+0.5 from threading webpage_context — makes downstream validators functional, even though duplicate fetch persists)
- token_efficiency: 2.5 (unchanged)
- aggregate: 3.4875 (+0.23)

### Lessons Learned
- Post-parse semantic validation with retry-note injection is a high-ROI reliability pattern even without touching the prompt. Gracefully-degrading validators (disable when reference data missing) prevent the pattern from becoming a liability offline.
- Iter 2 was a narrow, surgical change — 2 small quality additions and 1 real reliability improvement. The priority_fixes backlog from iter 1 (schema duplication, duplicate fetch, competitor consolidation, schema field reorder) was NOT touched. Need to prioritize these in iter 3 since they remain the highest-leverage changes.
- The semantic validator design is careful and good — worth keeping as reference for future validator layers.

## What to Focus On Next Iteration (iter 3, phase: mid→late)

Still active: prompt_quality, llm_configuration, retry_reliability, pipeline_structure. (token_efficiency activates at iter 4.)

Priority order unchanged from iter 1 memo because none of iter 1's priority_fixes were applied in iter 2:
1. **Delete embedded schema block from agent.py:265-268** — single highest-leverage change. Lifts llm_configuration to ~4.0-4.5.
2. **Fix duplicate fetch_webpage_context** — lru_cache on webpage.py:113, or thread through service.py. +0.5-1.0 on pipeline_structure.
3. **Reorder review-output-schema.json scores to {reason, score}** — one-line edit, CoT benefit.
4. **Consolidate competitor rule** (now 4 locations → 1 in SYSTEM_PROMPT). +0.5 on prompt_quality.
5. **Polish (low sev)**: rotate builders on semantic failure; Retry-After HTTP-date form parsing.

If iter 3 touches the embedded schema, verify builder 1 (grounded) still returns valid JSON — it can't use responseSchema (incompatible with google_search), so it relies on responseMimeType + prompt key list. Keep a short top-level key list in the prompt as its structure hint.

---

## Iter 3 Observations & Results (phase: late — token_efficiency now active)

### What got fixed in iter 3 (verified against current source)
1. **Embedded JSON schema dump REMOVED from build_review_packet (agent.py:301-302)** — the 80-line `json.dumps(schema, ensure_ascii=False, indent=2)` code-fenced block is gone. Replaced with a single prose line listing top-level keys (review_summary, persona_card, scores, strengths, findings, prioritized_improvements, open_questions) and per-finding field contract, plus a pointer to the API-side responseSchema enforcement. This is the single highest-leverage fix from the 3-iter backlog. Est. 500-700 token savings per call (partially offset by rubric).
2. **35-line scoring rubric added (agent.py:216-250)** — behavioral anchors at 1/3/5 for all 8 dimensions, with explicit anti-default-to-3/4 guidance and "say so in reason and score 3 with confidence note — do not inflate or guess" fallback. Real prompt-engineering quality, ~200-300 token cost.
3. **Prompt text now states `{reason, score}` ordering (agent.py:302)** — the prose output summary says "Each score is `{reason, score}`", attempting reasoning-before-commit via prompt. BUT see regression below.

### NEW ISSUE introduced in iter 3
- **Contradiction between prompt and enforced schema on score field order**: agent.py:302 declares `{reason, score}`, but review-output-schema.json:23-31 still has `{score, reason}`. _schema_from_template (agent.py:115, 117) propagates dict insertion order into both `required` and `propertyOrdering` of the responseSchema. On builders 2 and 3 (which attach the responseSchema), the constrained decoder emits {score, reason} at decode time — overriding the prompt text. CoT reasoning-before-commit is asserted in the prompt but defeated by the decoder. One-line fix: reorder the 8 score objects in review-output-schema.json.

### What was NOT addressed in iter 3 (all carries forward)
- review-output-schema.json still {score, reason} — now actively contradicts prompt.
- Duplicate fetch_webpage_context (service.py:18, service.py:90) — unchanged.
- No persona cache by (service, type, description) hash.
- Both stages hardcoded gemini-2.5-pro (service.py:17, 86, 140).
- SYSTEM_PROMPT still duplicated across gemini.py:394-405 systemInstruction AND agent.py:169-170 packet markdown.
- Competitor rule still 4× (SYSTEM_PROMPT + Known Competitors header + plain_text_fallback + enrich_persona).
- EVALUATE-not-EXPAND still 3× (SYSTEM_PROMPT + exec instructions 7-10 + reflection-loop bullets).
- 3 divergent builder shapes retained.
- Webpage excerpt still 4.4k tokens uncompressed (MAX_PAGES=8 × 2200 chars).
- Builder rotation coupled to API-attempt index — semantic-validation failure on attempt 0 does not rotate to a responseSchema-backed builder on attempt 1.
- Retry-After HTTP-date form still unparsed.

### Iter 3 Scores
- prompt_quality: 3.25 (+0.25 from scoring rubric + prose {reason, score} intent)
- llm_configuration: 3.75 (+0.25 from schema removed from prompt; offset partially by the new prompt/schema contradiction)
- retry_reliability: 4.75 (unchanged)
- pipeline_structure: 3.0 (unchanged)
- token_efficiency: 3.25 (+0.75 on first activation — schema block removal is a real ~300-500 net token saving after offsetting the rubric)
- aggregate: 3.6875 (+0.20 over iter 2's 3.4875)

### Lessons Learned
- The highest-leverage backlog item finally got done in iter 3. Three consecutive iterations of flagging the same fix eventually moved it; the trigger appears to be the diff narrative explicitly highlighting it as "flagged as highest-leverage open fix for three consecutive iterations."
- Removing the JSON schema from the prompt is correct, but it is only half the move — without also fixing the source schema file's field order, the prompt's new {reason, score} claim is actively overridden by the enforced responseSchema. This surfaces a general rule: when prompt and constrained-decoding schema disagree, the decoder wins and the prompt text becomes noise.
- Adding the behavioral-anchor rubric alongside the schema removal is a clever net-positive: it replaces brittle prompt-as-spec tokens with model-quality tokens.

## What to Focus On Next Iteration (iter 4, final-phase: late)

All 5 criteria now active. Order by leverage × low cost:
1. **Fix review-output-schema.json score field order** to `{reason, score}` (8 lines, propagates through agent.py:_schema_from_template into propertyOrdering+required on the responseSchema). This is a one-minute edit that completes iter 3's CoT intent. +0.25-0.5 on llm_configuration and prompt_quality.
2. **Duplicate fetch_webpage_context** — simplest viable is @functools.lru_cache on webpage.py:113. Alternatively thread webpage_context through service.py so the form handler crawls once and both persona enrichment + review share the snapshot. +0.5-1.0 on pipeline_structure.
3. **SYSTEM_PROMPT duplication** — keep only in systemInstruction on all 3 builders (currently only builder 1 has systemInstruction), delete the '## System Prompt' block from build_review_packet. +0.25-0.5 on token_efficiency (prefix-caching friendliness) and prompt_quality.
4. **Consolidate competitor rule 4→1 and EVALUATE-not-EXPAND 3→1** — see priority_fixes. +0.25-0.5 on prompt_quality.
5. **Model tier split** — gemini-2.5-flash for enrich_persona, keep -pro for run_review. Real cost saving, not a score-mover.
6. **Polish** — builder rotation on semantic failure, Retry-After HTTP-date, webpage relevance filter (top-K by persona terms).

The fix set for iter 4-5 is now well-known and small. Iter 3 cleared the single largest blocker; remaining work is consolidation and topology cleanup rather than new architecture.

---

## Iter 4 Observations & Results (phase: late)

### What got fixed in iter 4 (verified against current source)
1. **Score field order reversed in review-output-schema.json (lines 24-31)** — all 8 score objects now `{reason, score}` instead of `{score, reason}`. Because _schema_from_template (agent.py:109-118) propagates dict insertion order into both `required` and `propertyOrdering` of the responseSchema, builders 2 (inline) and 3 (plain-text fallback) now have constrained-decode-level enforcement of reasoning-before-commit. The prompt/schema contradiction introduced in iter 3 is resolved: agent.py:302 says `{reason, score}` and the decoder now agrees.
2. **@functools.lru_cache(maxsize=64) on fetch_webpage_context (webpage.py:3, 114)** — the duplicate-crawl bug flagged since iter 1 is fixed. service.py:90 (generate_persona_from_form) and service.py:18 (build_packet_for_brief) now share a single HTTP round-trip + parse per URL within a process. The cache is process-local with no TTL — fine for single-request lifetime, not a cross-run persistent cache.
3. **Journey_stage enum tightening (bonus)** — diff notes journey_stage pipe-enum ('Entry|Orientation|...') is now converted by _schema_from_template (agent.py:138-142) to a strict JSON-schema enum `{type: "string", enum: [...]}` on the responseSchema. Additional structural guarantee on strengths[].journey_stage and findings[].journey_stage for builders 2/3. Builder 1 (google_search) cannot carry responseSchema per Gemini API and relies on responseMimeType + prompt.
4. **webapp.py Regenerate button** — not relevant to prompt_pipeline criteria.

### What was NOT addressed in iter 4 (explicitly called out in diff)
- SYSTEM_PROMPT still duplicated across gemini.py:394-405 systemInstruction + agent.py:169-170 packet markdown.
- Competitor rule still 4× (agent.py:46-52 + agent.py:195 + gemini.py:472 + gemini.py:521-526).
- EVALUATE-not-EXPAND still 3× (agent.py:23-37 + exec instructions 7-10 + reflection-loop bullets).
- 3 divergent builder shapes retained.
- No persona cache by (service, type, description) hash.
- Both stages hardcoded gemini-2.5-pro (service.py:17, 86, 140).
- Webpage excerpt still 4.4k tokens uncompressed (MAX_PAGES=8 × MAX_EXCERPT_CHARS=2200).
- Builder rotation coupled to API-attempt index.
- Retry-After HTTP-date form unparsed.

### Iter 4 Scores
- prompt_quality: 3.5 (+0.25 from prompt/schema ordering contradiction being resolved at the decoder layer — prompt declaration now actually holds)
- llm_configuration: 4.25 (+0.5 from constrained-decode-enforced {reason, score} ordering + journey_stage strict enum on 2 of 3 builders)
- retry_reliability: 4.75 (unchanged)
- pipeline_structure: 3.75 (+0.75 from duplicate-fetch finally fixed — the most important carryover item from iter 1)
- token_efficiency: 3.5 (+0.25 from lru_cache eliminating the second crawl's HTTP+parse cost)
- aggregate: 4.0 (+0.31 over iter 3's 3.6875; target achieved)

### Lessons Learned
- Iter 4 closed the top two flagged carryover items (score-order + duplicate-fetch) with surgical 1-2 line changes. Total code delta was small; score delta was substantial (+0.31). This confirms a pattern: low-LoC / high-ROI fixes accumulate when the evaluator keeps flagging them iter after iter — eventually one clears.
- The bonus journey_stage enum expansion is worth noting: _schema_from_template's pipe-enum handling (agent.py:138-142) was already in place, so the structural tightening came "for free" once the schema file was touched. This is good prompt-engineering infrastructure: the schema-compilation path is expressive and small changes to the source schema propagate correctly.
- Key principle reinforced from iter 3: when prompt and constrained-decoding schema disagree, the decoder wins. Iter 4's fix was not to change the prompt — it was to change the schema so the decoder's output matches the prompt's stated contract. General lesson: prompt text is a weak statement about JSON structure in the presence of a responseSchema; make the schema the source of truth and let the prompt mirror it, not the other way around.

## What to Focus On Next Iteration (iter 5, final)

Remaining backlog is consolidation/topology cleanup. Order by leverage × low cost:
1. **SYSTEM_PROMPT duplication** — delete the '## System Prompt' block from build_review_packet (agent.py:169-170); add systemInstruction with SYSTEM_PROMPT to builders 2 and 3 (gemini.py:422-449, 452-481). All 3 builders then share one canonical source. +0.25-0.5 on prompt_quality and token_efficiency (~600 tokens/call saved, prompt-cache friendly prefix).
2. **Consolidate competitor rule 4→1 and EVALUATE-not-EXPAND 3→1** — concrete edits in priority_fixes. +0.25 on prompt_quality, +0.25 on token_efficiency.
3. **Persona cache by (service, type, description) hash** in service.py + model tier split (gemini-2.5-flash for enrich_persona) — real cost saving and +0.25 on pipeline_structure.
4. **Webpage relevance filter** (webpage.py) — top-K chunks by persona-term overlap, or lower MAX_EXCERPT_CHARS for non-landing pages. +0.25 on token_efficiency.
5. **Polish** — builder rotation decoupling on semantic failure, Retry-After HTTP-date form. Low ROI but tidy.

Aggregate 4.0 is at target (iter 0's target_score=4.0). Any combination of items 1-4 above in iter 5 could push aggregate to ~4.25-4.5. Realistic upper bound without architectural change is ~4.5 (builder 1's inability to carry responseSchema is an inherent cap on llm_configuration, and the webpage excerpt is a fundamental context-size choice).
