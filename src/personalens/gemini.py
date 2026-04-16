from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class GeminiError(Exception):
    pass


@dataclass
class GeminiConfig:
    model: str = "gemini-2.5-pro"
    api_key_env: str = "GEMINI_API_KEY"
    endpoint_base: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout_seconds: int = 45


def run_review(
    packet_markdown: str,
    schema: dict,
    config: GeminiConfig,
    raw_output_path: Path | None = None,
) -> dict:
    api_key = normalize_api_key(os.getenv(config.api_key_env, ""))
    if not api_key:
        raise GeminiError(f"{config.api_key_env} is not set")

    previous_failure = ""
    last_response_json: dict | None = None
    last_error_text = ""
    request_dump_path = raw_output_path.with_name("gemini-last-request.json") if raw_output_path is not None else None
    error_dump_path = raw_output_path.with_name("gemini-last-error.txt") if raw_output_path is not None else None

    for request_builder in REQUEST_BUILDERS:
        for _ in range(2):
            request_body = request_builder(packet_markdown, previous_failure)
            if request_dump_path is not None:
                request_dump_path.write_text(json.dumps(request_body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                response_json = _make_request(config, api_key, request_body)
            except GeminiError as exc:
                last_error_text = str(exc)
                if error_dump_path is not None:
                    error_dump_path.write_text(last_error_text + "\n", encoding="utf-8")
                previous_failure = f"The previous request failed at the API layer: {last_error_text}"
                continue

            last_response_json = response_json
            if raw_output_path is not None:
                raw_output_path.write_text(json.dumps(response_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            text = extract_text(response_json)
            if not text:
                previous_failure = "The previous response had no candidate text. Return a populated JSON review."
                continue

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                previous_failure = f"The previous response was invalid JSON: {exc}. Return valid JSON only."
                continue

            validation_error = validate_review_output(parsed)
            if not validation_error:
                return parsed

            previous_failure = f"The previous response was structurally empty: {validation_error}. Return a populated review."

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
        raise GeminiError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GeminiError(f"Network error: {exc}") from exc

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


def build_request_with_system_instruction(packet_markdown: str, previous_failure: str) -> dict:
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
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }


def build_request_inline_prompt(packet_markdown: str, previous_failure: str) -> dict:
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
        "generationConfig": {
            "responseMimeType": "application/json",
        },
    }


def build_request_plain_text_fallback(packet_markdown: str, previous_failure: str) -> dict:
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Return a JSON object only. No markdown. No explanation. "
                            "Fill every top-level section with real content, not null.\n\n"
                            + packet_markdown
                            + (f"\n\n## Retry Note\n- {previous_failure}" if previous_failure else "")
                        )
                    }
                ],
            }
        ]
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

    # First attempt: with Google Search grounding for web research
    request_body_grounded = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    # Fallback: without grounding (in case the API doesn't support it)
    request_body_plain = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    for request_body in [request_body_grounded, request_body_plain]:
        try:
            response_json = _make_request(config, api_key, request_body)
            text = extract_text(response_json)
            if text:
                return json.loads(text)
        except (GeminiError, json.JSONDecodeError):
            continue

    raise GeminiError("Persona enrichment returned empty response")
