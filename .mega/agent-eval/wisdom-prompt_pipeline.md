# Wisdom Cheatmap — Prompt & LLM Pipeline Engineering
## Session: prompt_pipeline | Event: optimize/step4/curate

---

## Strategy 1: Native Structured Output via responseSchema API Attachment
<!-- wisdom_id: 10cf3d1b2b1b4383:10cf3d1b2b1b4383:10cf3d1b2b1b4383 -->

**Symptom addressed**: responseSchema is computed and saved to disk but never attached to the API call — the schema only lives as an 80-line JSON dump embedded in the prompt text.

**Fix**: Attach the schema directly to the `generationConfig.responseSchema` field in the Gemini API request. Set `responseMimeType: "application/json"` alongside it. Remove the inline JSON schema block from the prompt entirely.

```python
generation_config = genai.GenerationConfig(
    response_mime_type="application/json",
    response_schema=build_response_json_schema(),
    temperature=0.2,
)
response = model.generate_content(contents, generation_config=generation_config)
```

**Why it works**: The Gemini API enforces the schema at the decode layer — constrained decoding guarantees the output conforms without requiring the model to "read" and follow the schema in the prompt. Removing the embedded schema saves 500–800 tokens per call and eliminates a brittle prompt-as-spec pattern.

**Schema field ordering fix**: Reorder score fields to `{reason, score}` rather than `{score, reason}` in the schema definition. Chain-of-thought works best when the model commits the justification before the numeric value — this is the reasoning-before-commit principle.

---

## Strategy 2: HTTP Status Classification and Exponential Backoff with Jitter
<!-- wisdom_id: 0c45632938aff2c2:0c45632938aff2c2:0c45632938aff2c2 -->

**Symptom addressed**: 6-attempt retry loop with no sleep/backoff/jitter/Retry-After parsing; 400/401/429/5xx/safety-blocks all retry identically.

**Fix**: Classify HTTP errors before retrying. Implement exponential backoff with full jitter. Parse the `Retry-After` header when present.

```python
import random, time

NON_RETRYABLE = {400, 401, 403}  # bad request, auth failure — do not retry
RETRYABLE     = {429, 500, 502, 503, 504}

def call_with_backoff(fn, max_attempts=6, base_delay=1.0, cap=60.0):
    for attempt in range(max_attempts):
        try:
            return fn()
        except google.api_core.exceptions.GoogleAPICallError as e:
            status = e.code if hasattr(e, 'code') else None
            if status in NON_RETRYABLE:
                raise  # never retry auth/bad-request errors
            if attempt == max_attempts - 1:
                raise
            # Parse Retry-After if present
            retry_after = getattr(e, 'retry_after', None)
            if retry_after:
                time.sleep(float(retry_after))
            else:
                # Full jitter: sleep in [0, min(cap, base * 2^attempt)]
                ceiling = min(cap, base_delay * (2 ** attempt))
                time.sleep(random.uniform(0, ceiling))
        except Exception:
            # Safety blocks, content policy — do not retry
            raise
```

**Why it works**: Retrying 400/401 wastes quota and adds latency with zero chance of success. Retrying safety blocks may re-trigger the same filter. Exponential backoff with jitter prevents thundering-herd on 429s. Retry-After parsing respects the server's cooling window precisely.

---

## Strategy 3: Retry Loop with Error Class Discrimination
<!-- wisdom_id: ef5cbec0bbe75670:ef5cbec0bbe75670:ef5cbec0bbe75670 -->

**Symptom addressed**: No distinction between transient (429, 5xx) and permanent (400, 401, safety block) failures in the retry path.

**Fix**: Wrap all Gemini calls in a central dispatcher that catches specific exception types and routes them to the correct handler — raise immediately for non-transient, sleep-and-retry for transient, log-and-skip for content-policy blocks.

```python
from google.api_core import exceptions as google_exc

RETRYABLE_EXCEPTIONS = (
    google_exc.ResourceExhausted,   # 429
    google_exc.ServiceUnavailable,  # 503
    google_exc.InternalServerError, # 500
    google_exc.DeadlineExceeded,    # timeout
)
NON_RETRYABLE_EXCEPTIONS = (
    google_exc.InvalidArgument,     # 400
    google_exc.PermissionDenied,    # 403
    google_exc.Unauthenticated,     # 401
)
```

**Why it works**: Discriminating on exception type rather than blind catch-all eliminates wasted retries and exposes real misconfiguration errors (wrong API key, malformed request) that would otherwise be silently swallowed after 6 slow retries.

---

## Strategy 4: Response Caching to Eliminate Redundant API Calls
<!-- wisdom_id: 7173f0f78b3ec9ad:7173f0f78b3ec9ad:7173f0f78b3ec9ad -->

**Symptom addressed**: `fetch_webpage_context` called twice per request (once for persona, once for review) with no memoization. No persona cache by `(service, type, description)` hash.

**Fix**: Implement two independent caches using the Cache-Aside pattern.

**Webpage cache** — keyed by URL, TTL-based (pages change):
```python
import hashlib, functools

@functools.lru_cache(maxsize=256)
def fetch_webpage_context_cached(url: str) -> str:
    return fetch_webpage_context(url)
```

**Persona cache** — keyed by `(service, persona_type, description)` hash, longer TTL (personas are stable):
```python
def _persona_key(service: str, persona_type: str, description: str) -> str:
    raw = f"{service}|{persona_type}|{description}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

_persona_cache: dict[str, PersonaResult] = {}

def get_or_generate_persona(service, persona_type, description, generate_fn):
    key = _persona_key(service, persona_type, description)
    if key in _persona_cache:
        return _persona_cache[key]
    result = generate_fn(service, persona_type, description)
    _persona_cache[key] = result
    return result
```

**Why it works**: Each duplicate `fetch_webpage_context` call is a full HTTP round-trip. Persona generation is a multi-second LLM call — caching by content hash means identical persona requests (common in batch evaluation) cost one call instead of N. Combined, these two caches can cut API spend in half for typical evaluation workloads.

---

## Strategy 5: Cache-Aside Pattern for Persona and Webpage Memoization
<!-- wisdom_id: d51bf699a25a14f1:d51bf699a25a14f1:d51bf699a25a14f1 -->

**Symptom addressed**: No persistent caching layer between pipeline runs — every evaluation re-fetches and re-generates from scratch.

**Fix**: Apply the Cache-Aside pattern with explicit invalidation. For in-process caching, `functools.lru_cache` or a dict with TTL is sufficient. For cross-process or cross-run caching, use a lightweight file-backed store:

```python
import json, time
from pathlib import Path

CACHE_DIR = Path(".mega/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def cache_get(key: str, ttl_seconds: int = 3600):
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        data = json.loads(path.read_text())
        if time.time() - data["ts"] < ttl_seconds:
            return data["value"]
    return None

def cache_set(key: str, value):
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({"ts": time.time(), "value": value}))
```

**Why it works**: Persisting cache across runs eliminates redundant LLM calls during iterative development and re-evaluation. The TTL ensures stale webpage content or updated persona logic is refreshed automatically.

---

## Strategy 6: Prompt Deduplication via Static Block Isolation
<!-- wisdom_id: f16fac9d3ec5b92d:f16fac9d3ec5b92d:f16fac9d3ec5b92d -->

**Symptom addressed**: Competitor rule restated 3×, "EVALUATE not EXPAND" restated 3×, SYSTEM_PROMPT duplicated in both `systemInstruction` and packet markdown.

**Fix**: Isolate static system prompt content into a single canonical location — the `system_instruction` parameter of the Gemini API. Remove all repetition from the user-turn prompt body.

```python
# BAD: system prompt duplicated in both fields
request = {
    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    "contents": [{"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}]
}

# GOOD: single source of truth
request = {
    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
    "contents": [{"role": "user", "parts": [{"text": user_prompt}]}]
}
```

**Repeated-rule consolidation**: Merge all instances of the same constraint into one occurrence. For example, the competitor evaluation rule and "EVALUATE not EXPAND" should each appear exactly once in the system instruction. Repetition does not strengthen instruction-following; it wastes tokens and can confuse the model about which instance is authoritative.

**Why it works**: Duplicate content in both `systemInstruction` and user message doubles token cost for those sections. Repeated rules in the prompt body waste ~200–400 tokens per call with no reliability benefit. Placing stable constraints in `systemInstruction` also enables prompt caching on supported endpoints.

---

## Strategy 7: Deterministic Generation Config and Temperature Control
<!-- wisdom_id: 95d85c9d68c6a878:95d85c9d68c6a878:95d85c9d68c6a878 -->

**Symptom addressed**: No temperature set anywhere — Gemini 2.5 Pro defaults to ~1.0, producing high variance in structured scoring responses.

**Fix**: Set temperature explicitly in `GenerationConfig`. For evaluation/scoring pipelines, use a low temperature (0.0–0.2). Consolidate all three divergent request-builder shapes into one canonical builder.

```python
EVAL_GENERATION_CONFIG = genai.GenerationConfig(
    temperature=0.2,          # deterministic enough for scoring, slight variance for persona creativity
    top_p=0.95,
    max_output_tokens=2048,
    response_mime_type="application/json",
    response_schema=build_response_json_schema(),
)

# Single canonical request builder — replaces 3 divergent shapes
def build_request(system_prompt: str, user_prompt: str) -> dict:
    return {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": EVAL_GENERATION_CONFIG.to_dict(),
    }
```

**Why it works**: At temperature=1.0, the same input can produce significantly different numeric scores across runs — this breaks reproducibility and makes A/B evaluation unreliable. A single canonical `build_request` function eliminates the three divergent shapes (persona builder, review builder, schema builder), making the codebase auditable and ensuring `generationConfig` is always applied consistently.

---

## Token Budget Summary

| Symptom | Current Token Cost | After Fix |
|---|---|---|
| Embedded response schema in prompt | +500–800 tokens/call | 0 (moved to API param) |
| SYSTEM_PROMPT in both systemInstruction and user message | +~600 tokens/call | 0 |
| Competitor rule × 3 + EVALUATE rule × 3 | +~300 tokens/call | ~100 tokens (×1 each) |
| 4.4k webpage excerpt (no relevance filter) | 4,400 tokens/call | ~1,500 (top-K relevant chunks) |
| Duplicate fetch_webpage_context calls | 2× HTTP + 2× tokens | 1× (memoized) |

**Estimated total savings: ~1,800–2,500 tokens per pipeline invocation** before persona caching. With persona caching on repeated (service, type, description) inputs, LLM call count reduction dominates cost.
