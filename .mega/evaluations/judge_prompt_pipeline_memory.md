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

## What to Focus On Next Iteration (iter 1, phase: early)
Priority fixes are for critical criteria only (prompt_quality, llm_configuration, retry_reliability).

Highest-leverage single change: **wire up `responseSchema` + set `temperature: 0.1`** in all builders. The schema object (`packet.response_json_schema`) is already computed — just plumb it to `generationConfig`. This should:
- Cut ~500-800 tokens/call (remove embedded schema block)
- Eliminate most JSON parse failures (constrained decoding)
- Unlock +1.5-2 points on llm_configuration AND improve token_efficiency

Second-highest: **retry classification + exponential backoff**. Introduce `GeminiTransientError` / `GeminiPermanentError` / `GeminiRateLimitError`, parse HTTP status + Retry-After, add backoff with jitter, cap at 3 total attempts. Unlocks +1.5 on retry_reliability.

Third: **dedupe restatements**. Single canonical competitor rule in SYSTEM_PROMPT. Single canonical EVALUATE-not-EXPAND. Reorder `review-output-schema.json` scores to `{reason, score}`. Unlocks +1 on prompt_quality, +0.5 on token_efficiency.

Watch for: when schema is moved to responseSchema, the `validate_review_output` function may become redundant for structural checks but remains useful for semantic-emptiness checks — keep it. Also watch that the 3rd "plain text fallback" builder isn't relied upon; consider deleting it.

## Lessons / Results (will fill in iter 1+)
- (none yet)
