from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class GeminiError(Exception):
    pass


class GeminiPermanentError(GeminiError):
    """Client-side error (4xx except 429): invalid request, auth failure, content filter. Do not retry."""


class GeminiRateLimitError(GeminiError):
    """HTTP 429. Retry honoring the server's Retry-After if present."""

    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class GeminiTransientError(GeminiError):
    """5xx / network / timeout. Retry with exponential backoff + full jitter."""


_MAX_ATTEMPTS = 3
_BASE_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0


@dataclass
class GeminiConfig:
    model: str = "gemini-2.5-pro"
    api_key_env: str = "GEMINI_API_KEY"
    endpoint_base: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout_seconds: int = 45
    temperature: float = 0.1
    top_p: float = 0.95


def _exponential_backoff(attempt: int) -> float:
    capped = min(_MAX_BACKOFF_SECONDS, _BASE_BACKOFF_SECONDS * (2 ** attempt))
    return random.uniform(0.0, capped)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def _finish_reason(response_json: dict) -> str:
    candidates = response_json.get("candidates") or []
    if not candidates:
        return ""
    return ((candidates[0] or {}).get("finishReason") or "").strip()


_UNOBSERVABLE_PHRASES = (
    "not observable",
    "not visible",
    "js-rendered",
    "js rendered",
    "javascript",
    "dynamically loaded",
    "dynamic content",
    "runtime content",
    "requires interaction",
    "after login",
    "behind the login",
)


_TITLECASE_MULTIWORD = re.compile(
    r"\b[A-Z][A-Za-z0-9+][A-Za-z0-9+\-]{0,23}(?:\s+[A-Z][A-Za-z0-9+][A-Za-z0-9+\-]{0,23}){1,4}\b"
)


# Multi-word title-cased tokens that are part of the packet scaffolding (section headers, enum values
# for severity / journey stages / scoring dimensions). Safelisting these prevents false positives
# where the model legitimately quotes the structure we taught it in the prompt. This list is
# deliberately keyed to packet structure only, not to any specific user input or website content.
_PACKET_SAFELIST = frozenset(
    s.casefold() for s in (
        "System Prompt", "Review Goal", "Persona Card", "Known Competitors",
        "Website Context", "Journey Stages", "Scoring Dimensions",
        "Execution Instructions", "Reflection Loop", "Retry Note",
        "Required Output Schema", "Core Journey", "Business Goal",
        "Open Questions", "Quick Wins", "Structural Fixes", "Validation Experiments",
        "Target User", "Pain Points", "Task Clarity", "Task Success",
        "Effort Load", "Trust Confidence", "Value Communication",
        "Error Recovery", "Emotional Fit", "Follow Up", "Retention Cue",
        "Access Needs", "Decision Style", "Device Context", "Technical Level",
        "Success Definition", "Evidence Sources", "Web Research Summary",
        "Task Start", "Core Action", "Journey Stage", "Journey Stages",
        "Review Packet", "Review Summary", "Persona Voice",
    )
)


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _check_evidence_grounding(parsed: dict, webpage_context: str) -> list[str]:
    """Return human-readable issues for findings whose `evidence` isn't grounded in the crawled page.

    An evidence field is considered grounded if (a) any 3-consecutive-word window of it (normalized)
    appears in the webpage_context (normalized), OR (b) it explicitly admits the signal is not
    observable from static HTML (e.g., JS-rendered / dynamic). Missing webpage_context disables the
    check entirely so the pipeline remains usable offline.
    """
    if not webpage_context:
        return []
    context_norm = _normalize_for_match(webpage_context)
    issues: list[str] = []
    findings = parsed.get("findings") or []
    for idx, finding in enumerate(findings):
        if not isinstance(finding, dict):
            continue
        evidence = finding.get("evidence") or ""
        if not isinstance(evidence, str) or not evidence.strip():
            continue
        evidence_norm = _normalize_for_match(evidence)
        if any(p in evidence_norm for p in _UNOBSERVABLE_PHRASES):
            continue
        tokens = evidence_norm.split()
        if len(tokens) < 3:
            continue
        windows = (" ".join(tokens[i:i + 3]) for i in range(len(tokens) - 2))
        if any(w in context_norm for w in windows):
            continue
        title = finding.get("title") or f"finding[{idx}]"
        issues.append(
            f"finding '{title}': evidence not grounded in the crawled website context "
            "(no 3-word window matched, and the evidence does not admit 'not observable / JS-rendered / dynamic')"
        )
    return issues


def _check_competitor_leak(
    parsed: dict,
    allowed_competitors: list[str] | None,
    webpage_context: str,
) -> list[str]:
    """Return title-cased multi-word tokens appearing in findings/strengths that are neither in the
    user-approved competitor list nor present in the crawled website context.

    Pattern detection is grammatical (multi-word title case), not content-specific: no hardcoded
    brand list. The packet-scaffolding safelist only excludes section headers and enum values that
    the LLM was instructed to quote verbatim.

    Returns an empty list when BOTH `allowed_competitors` and `webpage_context` are empty — without
    either reference there is no way to discriminate legitimate multi-word terms from leaked product
    names, so the check is disabled instead of flagging every idiom.
    """
    allowed_norm = {c.strip().casefold() for c in (allowed_competitors or []) if isinstance(c, str) and c.strip()}
    context_norm = _normalize_for_match(webpage_context or "")
    if not allowed_norm and not context_norm:
        return []
    # Wrap context with spaces so substring checks behave as word-boundary checks
    # (prevents e.g. "Stripe" being masked by "restrictions" via raw substring containment).
    context_padded = f" {context_norm} " if context_norm else ""

    def _scan_fields():
        for key in ("findings", "strengths"):
            items = parsed.get(key) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                for fkey in ("title", "problem", "evidence", "improvement_direction", "persona_reason"):
                    v = item.get(fkey)
                    if isinstance(v, str):
                        yield v

    found: set[str] = set()
    for text in _scan_fields():
        for match in _TITLECASE_MULTIWORD.finditer(text):
            token = match.group(0).strip()
            token_norm = token.casefold()
            if token_norm in _PACKET_SAFELIST:
                continue
            # Allowed competitors: match whole token, or token is multi-word-substring of an allowed entry (or vice versa).
            if any(token_norm == a or f" {token_norm} " in f" {a} " or f" {a} " in f" {token_norm} " for a in allowed_norm):
                continue
            # Website context: require word-boundary presence of the token in the crawled page.
            if context_padded and f" {token_norm} " in context_padded:
                continue
            found.add(token)
    return sorted(found)


def run_review(
    packet_markdown: str,
    schema: dict,
    config: GeminiConfig,
    raw_output_path: Path | None = None,
    webpage_context: str | None = None,
    allowed_competitors: list[str] | None = None,
) -> dict:
    api_key = normalize_api_key(os.getenv(config.api_key_env, ""))
    if not api_key:
        raise GeminiError(f"{config.api_key_env} is not set")

    previous_failure = ""
    last_response_json: dict | None = None
    last_error_text = ""
    request_dump_path = raw_output_path.with_name("gemini-last-request.json") if raw_output_path is not None else None
    error_dump_path = raw_output_path.with_name("gemini-last-error.txt") if raw_output_path is not None else None

    for attempt in range(_MAX_ATTEMPTS):
        request_builder = REQUEST_BUILDERS[min(attempt, len(REQUEST_BUILDERS) - 1)]
        request_body = request_builder(packet_markdown, previous_failure, config=config, schema=schema)
        if request_dump_path is not None:
            request_dump_path.write_text(json.dumps(request_body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        try:
            response_json = _make_request(config, api_key, request_body)
        except GeminiPermanentError as exc:
            # 4xx (excl 429): stop retrying — the request will fail identically on retry
            last_error_text = str(exc)
            if error_dump_path is not None:
                error_dump_path.write_text(last_error_text + "\n", encoding="utf-8")
            raise
        except GeminiRateLimitError as exc:
            last_error_text = str(exc)
            if error_dump_path is not None:
                error_dump_path.write_text(last_error_text + "\n", encoding="utf-8")
            if attempt < _MAX_ATTEMPTS - 1:
                sleep_for = exc.retry_after_seconds if exc.retry_after_seconds is not None else _exponential_backoff(attempt)
                time.sleep(min(sleep_for, _MAX_BACKOFF_SECONDS))
            previous_failure = f"Previous request was rate-limited ({last_error_text}). Keep the response concise."
            continue
        except GeminiTransientError as exc:
            last_error_text = str(exc)
            if error_dump_path is not None:
                error_dump_path.write_text(last_error_text + "\n", encoding="utf-8")
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_exponential_backoff(attempt))
            previous_failure = f"The previous request failed at the API layer: {last_error_text}"
            continue

        last_response_json = response_json
        if raw_output_path is not None:
            raw_output_path.write_text(json.dumps(response_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        text = extract_text(response_json)
        if not text:
            finish_reason = _finish_reason(response_json)
            if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
                raise GeminiPermanentError(
                    f"Response blocked by content safety (finishReason={finish_reason})."
                )
            previous_failure = "The previous response had no candidate text. Return a populated JSON review."
            continue

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            previous_failure = f"The previous response was invalid JSON: {exc}. Return valid JSON only."
            continue

        validation_error = validate_review_output(parsed)
        if validation_error:
            previous_failure = f"The previous response was structurally empty: {validation_error}. Return a populated review."
            continue

        semantic_issues: list[str] = []
        if webpage_context:
            semantic_issues.extend(_check_evidence_grounding(parsed, webpage_context))
        leak = _check_competitor_leak(parsed, allowed_competitors, webpage_context or "")
        if leak:
            semantic_issues.append(
                "unapproved product names appeared in findings/strengths: "
                + ", ".join(f"'{name}'" for name in leak[:5])
                + ". Only names in Known Competitors or the crawled website context may be used."
            )

        if not semantic_issues:
            return parsed

        # Last attempt: accept rather than starving the loop when a genuine term couldn't be anchored.
        if attempt >= _MAX_ATTEMPTS - 1:
            return parsed

        previous_failure = (
            "Semantic validation failed. Rewrite the review addressing these issues: "
            + "; ".join(semantic_issues[:3])
        )

    raise GeminiError(
        "Model returned an empty or invalid review after retry"
        + (f". Last API error: {last_error_text}" if last_error_text else "")
        + (f". Last response excerpt: {json.dumps(last_response_json, ensure_ascii=False)[:500]}" if last_response_json else "")
    )


def _make_request(config: GeminiConfig, api_key: str, request_body: dict) -> dict:
    url = f"{config.endpoint_base}/models/{config.model}:generateContent?key={api_key}"
    payload = json.dumps(request_body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        code = exc.code
        if code == 429:
            retry_after = _parse_retry_after(exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None)
            raise GeminiRateLimitError(f"HTTP 429: {detail}", retry_after_seconds=retry_after) from exc
        if 400 <= code < 500:
            raise GeminiPermanentError(f"HTTP {code}: {detail}") from exc
        raise GeminiTransientError(f"HTTP {code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GeminiTransientError(f"Network error: {exc}") from exc

    return json.loads(raw)


def extract_text(response_json: dict) -> str:
    candidates = response_json.get("candidates") or []
    if not candidates:
        return ""

    parts = (((candidates[0] or {}).get("content") or {}).get("parts")) or []
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "".join(texts).strip()


def validate_review_output(data: dict) -> str:
    for key in ["review_summary", "persona_card", "scores", "prioritized_improvements"]:
        if data.get(key) in (None, {}, []):
            return f"{key} is empty"

    if not data.get("strengths") and not data.get("findings"):
        return "both strengths and findings are empty"

    return ""


def normalize_api_key(value: str) -> str:
    cleaned = (
        value.strip()
        .strip("\"'")
        .strip("‘’“”")
        .replace("\u2018", "")
        .replace("\u2019", "")
        .replace("\u201c", "")
        .replace("\u201d", "")
    )
    return "".join(ch for ch in cleaned if ch.isprintable() and ord(ch) >= 32)


def _base_generation_config(config: GeminiConfig | None) -> dict:
    cfg = config or GeminiConfig()
    return {
        "responseMimeType": "application/json",
        "temperature": cfg.temperature,
        "topP": cfg.top_p,
    }


def build_request_with_system_instruction(
    packet_markdown: str,
    previous_failure: str,
    config: GeminiConfig | None = None,
    schema: dict | None = None,
) -> dict:
    # Note: google_search tool is incompatible with responseSchema on Gemini.
    # Keep responseMimeType + temperature + topP; rely on prompt-embedded schema + mime type for structure.
    generation_config = _base_generation_config(config)
    return {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You are a persona-based quality review agent. "
                        "Return only valid JSON that matches the requested structure. "
                        "Do not return null for required top-level sections. "
                        "If evidence is limited, say so inside the JSON rather than returning an empty structure. "
                        "Use Google Search to research the service, its competitors, and user feedback to ground your review in real-world evidence."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": packet_markdown + (f"\n\n## Retry Note\n- {previous_failure}" if previous_failure else "")
                    }
                ],
            }
        ],
        "tools": [{"google_search": {}}],
        "generationConfig": generation_config,
    }


def build_request_inline_prompt(
    packet_markdown: str,
    previous_failure: str,
    config: GeminiConfig | None = None,
    schema: dict | None = None,
) -> dict:
    generation_config = _base_generation_config(config)
    if schema:
        generation_config["responseSchema"] = schema
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "You are a persona-based quality review agent. "
                            "Return only valid JSON. "
                            "Do not return null for required top-level sections.\n\n"
                            + packet_markdown
                            + (f"\n\n## Retry Note\n- {previous_failure}" if previous_failure else "")
                        )
                    }
                ],
            }
        ],
        "generationConfig": generation_config,
    }


def build_request_plain_text_fallback(
    packet_markdown: str,
    previous_failure: str,
    config: GeminiConfig | None = None,
    schema: dict | None = None,
) -> dict:
    # Final fallback: always include responseMimeType so a JSON parse attempt succeeds.
    # The competitor rule here compensates for the lack of systemInstruction.
    generation_config = _base_generation_config(config)
    if schema:
        generation_config["responseSchema"] = schema
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Return a JSON object only. No markdown. No explanation. "
                            "Fill every top-level section with real content, not null. "
                            "Do NOT mention any competitor or third-party product names unless they appear in the brief's Known Competitors list or in the provided website context.\n\n"
                            + packet_markdown
                            + (f"\n\n## Retry Note\n- {previous_failure}" if previous_failure else "")
                        )
                    }
                ],
            }
        ],
        "generationConfig": generation_config,
    }


REQUEST_BUILDERS = [
    build_request_with_system_instruction,
    build_request_inline_prompt,
    build_request_plain_text_fallback,
]


def enrich_persona(
    service_name: str,
    service_url: str,
    service_type: str,
    core_journey: str,
    persona_description: str,
    problems: list[str],
    business_goal: str,
    webpage_text: str,
    config: GeminiConfig | None = None,
) -> dict:
    """Call Gemini to generate a rich persona card from minimal user input."""
    config = config or GeminiConfig()
    api_key = normalize_api_key(os.getenv(config.api_key_env, ""))
    if not api_key:
        raise GeminiError(f"{config.api_key_env} is not set")

    problems_text = "\n".join(f"- {p}" for p in problems)
    webpage_snippet = webpage_text[:3000] if webpage_text else "No website text available."

    prompt = f"""You are a UX research expert. Based on the inputs below AND web research, generate a detailed persona card as JSON.

## Your Research Tasks
Before generating the persona, search the web for:
1. "{service_name}" — what this service does, user reviews, community feedback
2. "{service_type} user persona" — typical user profiles for this type of service
3. "{service_type} user pain points" — common frustrations users face

Use what you find to make the persona grounded in real-world data, not assumptions.

## CRITICAL RULE ON COMPETITORS AND OTHER PRODUCTS
- Do NOT infer, guess, or mention any specific competitor product names.
- Do NOT speculate about what tools this persona currently uses.
- Do NOT include any product names in goals, pain_points, context, or any other field unless they were explicitly provided in the user's inputs.
- Focus on the persona's characteristics, behaviors, and motivations — NOT on which tools they use.
- If you are tempted to mention a specific product, use a generic phrase instead (e.g., "existing tools in this category", "alternative solutions").

## Inputs
- Service: {service_name} ({service_type})
- URL: {service_url}
- Core journey: {core_journey}
- Business goal: {business_goal}
- User description: {persona_description}
- Known problems:
{problems_text}
- Website text (raw HTML extract, dynamic numbers may show as 0 — ignore those):
{webpage_snippet}

## Task
Generate a realistic, specific persona grounded in:
1. The user's description and problems (primary source)
2. Web research about this service and its user base (secondary source)
3. Industry knowledge about this service type (tertiary source)

Do NOT use generic placeholders. Be specific to THIS service and THIS user type.

Return JSON matching this exact structure:
{{
  "name": "A realistic name or role-based name (e.g., 'Sarah Kim — Startup PM')",
  "segment": "Specific user segment description",
  "job_to_be_done": "What they are trying to accomplish, specific to this service",
  "context": "When/why/how they arrive at this service — be specific, referencing real usage patterns found in research",
  "goals": ["goal1", "goal2", "goal3"],
  "pain_points": ["pain1", "pain2", "pain3"],
  "technical_level": "low|medium|high",
  "decision_style": "One of: cautious, fast, comparison-heavy, trust-driven, evidence-based",
  "device_context": "mobile|desktop|mixed",
  "access_needs": ["need1", "need2"],
  "success_definition": "What 'good' feels like to this persona — specific to this service",
  "voice": ["anchor1", "anchor2", "anchor3", "anchor4"],
  "evidence_sources": ["source1 — what was found", "source2 — what was found"],
  "confidence": "low|medium|high",
  "web_research_summary": "2-3 sentence summary of key findings from web research that informed this persona"
}}

IMPORTANT:
- Write values in English by default. If the user's inputs are predominantly in another language (e.g., Korean), match that language instead.
- Be specific to this service, not generic UX personas.
- voice anchors should reflect this person's communication style and emotional state.
- confidence should reflect how much evidence you have (higher if web research found strong signals).
- evidence_sources should include what you actually found from web research.
- web_research_summary should summarize the most relevant findings.
"""

    generation_config = _base_generation_config(config)

    # First attempt: with Google Search grounding for web research
    request_body_grounded = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": generation_config,
    }

    # Fallback: without grounding (in case the API doesn't support it)
    request_body_plain = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    last_transient_error: Exception | None = None
    for attempt, request_body in enumerate([request_body_grounded, request_body_plain]):
        try:
            response_json = _make_request(config, api_key, request_body)
        except GeminiPermanentError:
            # Bad request / auth / safety block — switching bodies will not help.
            raise
        except GeminiRateLimitError as exc:
            last_transient_error = exc
            sleep_for = exc.retry_after_seconds if exc.retry_after_seconds is not None else _exponential_backoff(attempt)
            time.sleep(min(sleep_for, _MAX_BACKOFF_SECONDS))
            continue
        except GeminiTransientError as exc:
            last_transient_error = exc
            time.sleep(_exponential_backoff(attempt))
            continue

        text = extract_text(response_json)
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue

    if last_transient_error is not None:
        raise GeminiError(f"Persona enrichment failed after retries: {last_transient_error}") from last_transient_error
    raise GeminiError("Persona enrichment returned empty response")
