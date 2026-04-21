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
