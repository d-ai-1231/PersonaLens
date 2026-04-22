from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

from .models import ReviewBrief, ValidationError


SYSTEM_PROMPT = dedent(
    """
    You are a persona-based quality review agent.
    Review the public pre-login website experience as a specific target user, not as a generic QA assistant.
    Keep the persona voice consistent, but anchor every claim in observable evidence.
    Separate observed friction from proposed solutions.
    Prioritize findings by user impact.
    Always distinguish evidence from inference.
    If evidence is weak or incomplete, say so explicitly and lower confidence.
    Focus especially on value clarity, trust, message hierarchy, CTA strength, and whether the site gives the persona a compelling reason to start onboarding.
    End with prioritized improvements and open questions.

    FUNDAMENTAL EVALUATION FRAMEWORK (this is non-negotiable):
    Your job is to EVALUATE whether the website effectively serves the user's STATED goals — NOT to expand or enhance random content you find on the site.

    The user has explicitly provided:
    - A business goal
    - A target persona
    - A core user journey
    - Known user problems

    Every finding and every recommendation MUST be anchored to these stated priorities.
    - If you find content on the website that does NOT serve the stated business goal or persona, flag it as noise/distraction and consider recommending its REMOVAL or de-emphasis — do NOT recommend expanding it.
    - If the website lacks content needed for the stated goal, recommend adding it.
    - Never recommend building out a feature or section just because it exists on the page. Ask: "Does this content serve the stated business goal and persona? If not, it is clutter, not an opportunity."
    - Every recommendation must answer: "How does this help the stated business goal or persona journey?"
    - When in doubt, prioritize the user's stated priorities over anything you observe on the site.

    Write the review in English by default. If the user's inputs (persona description, problems, business goal) are predominantly written in another language (e.g., Korean), match that language instead. Use natural, professional phrasing.

    CRITICAL: The website text you receive is extracted from raw HTML without JavaScript execution.
    This means dynamic content (counters, stats, real-time numbers, data loaded via API/JS) will appear as 0, empty, or as placeholder values.
    Do NOT flag zero values or empty dynamic counters as problems — they are artifacts of static HTML extraction, not actual issues on the live site.
    Focus your review on static content: copy, messaging, structure, CTAs, trust signals, and information hierarchy.

    CRITICAL RULE ON COMPETITORS AND THIRD-PARTY PRODUCTS:
    You may mention specific competitor or alternative product names ONLY if one of these is true:
    1. The user explicitly listed them in the "Known Competitors" section of the brief.
    2. The competitor name appears in the extracted website text (the target website itself mentions them).
    Do NOT mention any product name from Google Search results, general industry knowledge, or assumptions about what the persona might use.
    If you need to refer to alternatives generically, use phrases like "existing tools in this space", "alternative solutions", or "similar products" — never a specific brand name.
    Violating this rule produces misleading reviews. Be strict.
    """
).strip()


VALIDATION_CRITERIA = [
    "persona is specific and evidence-backed",
    "findings are tied to the persona journey",
    "each finding includes priority, evidence, and impact",
    "recommendations are actionable and prioritized",
    "the review includes both strengths and weaknesses",
    "the output avoids generic UX advice",
    "the output distinguishes observation from inference",
]


JOURNEY_STAGES = [
    "Entry",
    "Orientation",
    "Task start",
    "Core action",
    "Error recovery",
    "Completion",
    "Follow-up / Retention cue",
]


SCORING_DIMENSIONS = [
    "task_clarity",
    "task_success",
    "effort_load",
    "trust_confidence",
    "value_communication",
    "error_recovery",
    "accessibility",
    "emotional_fit",
]


@dataclass
class ReviewPacket:
    markdown: str
    output_skeleton: dict
    response_json_schema: dict


def load_schema(schema_path: Path) -> dict:
    return json.loads(schema_path.read_text(encoding="utf-8"))


def build_response_json_schema(template: dict) -> dict:
    schema = _schema_from_template(template)
    if isinstance(schema, dict):
        schema["additionalProperties"] = False
    return schema


def _schema_from_template(value):
    if isinstance(value, dict):
        properties = {key: _schema_from_template(item) for key, item in value.items()}
        return {
            "type": "object",
            "properties": properties,
            "required": list(value.keys()),
            "additionalProperties": False,
            "propertyOrdering": list(value.keys()),
        }

    if isinstance(value, list):
        item_schema = _schema_from_template(value[0]) if value else {"type": "string"}
        return {
            "type": "array",
            "items": item_schema,
        }

    if isinstance(value, bool):
        return {"type": "boolean"}

    if isinstance(value, int):
        if value == 1:
            return {"type": "integer", "minimum": 1, "maximum": 5}
        return {"type": "integer"}

    if isinstance(value, float):
        return {"type": "number"}

    if isinstance(value, str):
        if "|" in value:
            options = [part.strip() for part in value.split("|") if part.strip()]
            if options:
                return {"type": "string", "enum": options}
        return {"type": "string"}

    return {"type": "string"}


def build_review_packet(brief: ReviewBrief, schema: dict, webpage_context: str | None = None) -> ReviewPacket:
    issues = brief.validate()
    if issues:
        raise ValidationError(issues)

    evidence_lines = "\n".join(f"- {item}" for item in brief.evidence) if brief.evidence else "- No additional evidence provided."
    constraint_lines = "\n".join(f"- {item}" for item in brief.known_constraints) if brief.known_constraints else "- No special constraints provided."
    notes_lines = "\n".join(f"- {item}" for item in brief.notes) if brief.notes else "- No extra notes provided."
    if brief.competitors:
        competitor_lines = "\n".join(f"- {item}" for item in brief.competitors)
    else:
        competitor_lines = "- No competitors provided. You MUST NOT mention any specific competitor or alternative product names in your review. Use generic phrases only."
    journey_lines = "\n".join(f"- {item}" for item in JOURNEY_STAGES)
    dimension_lines = "\n".join(f"- {item}" for item in SCORING_DIMENSIONS)
    criteria_lines = "\n".join(f"- {item}" for item in VALIDATION_CRITERIA)
    persona = brief.persona

    markdown = "\n".join(
        [
            "# Review Packet",
            "",
            "## System Prompt",
            SYSTEM_PROMPT,
            "",
            "## Review Goal",
            f"- Service: {brief.service.name} ({brief.service.type})",
            f"- URL: {brief.service.url}",
            f"- Review goal: {brief.review_goal}",
            f"- Core journey: {brief.core_journey}",
            f"- Business goal: {brief.business_goal}",
            "",
            "## Persona Card",
            f"- Name: {persona.name}",
            f"- Segment: {persona.segment}",
            f"- Job to be done: {persona.job_to_be_done}",
            f"- Context: {persona.context}",
            f"- Goals: {', '.join(persona.goals)}",
            f"- Pain points: {', '.join(persona.pain_points)}",
            f"- Technical level: {persona.technical_level}",
            f"- Decision style: {persona.decision_style}",
            f"- Device context: {persona.device_context}",
            f"- Access needs: {', '.join(persona.access_needs)}",
            f"- Success definition: {persona.success_definition}",
            f"- Voice anchors: {', '.join(persona.voice)}",
            f"- Evidence sources: {', '.join(persona.evidence_sources)}",
            f"- Confidence: {persona.confidence}",
            "",
            "## Known Competitors (the ONLY product names you may mention)",
            competitor_lines,
            "",
            "## Evidence",
            evidence_lines,
            "",
            "## Website Context",
            webpage_context or "- No live website snapshot was provided.",
            "",
            "## Constraints",
            constraint_lines,
            "",
            "## Notes",
            notes_lines,
            "",
            "## Journey Stages To Review",
            journey_lines,
            "",
            "## Scoring Dimensions",
            dimension_lines,
            "",
            "## Scoring Rubric (1-5 behavioral anchors — use before writing any score)",
            "Score each dimension from 1 to 5. Do NOT default to 3 or 4 — the middle is reserved for genuinely middling evidence. Use half-points only if the behavior sits between two anchors.",
            "- **task_clarity** — Can the persona tell in the first screen what the service does and whether it applies to them?",
            "  - 1: Hero copy is a buzzword cloud; the persona leaves without forming a theory of the product.",
            "  - 3: Persona can guess the category but not what makes this product different or useful for their job.",
            "  - 5: Within 10 seconds the persona names the concrete capability relevant to their stated goal.",
            "- **task_success** — Can the persona get to the stated next step (onboarding / signup / core action) with the information given?",
            "  - 1: The required next step is missing, buried, or blocked by a login wall with no preview.",
            "  - 3: The next step exists but the persona must guess what happens after; friction is real but surmountable.",
            "  - 5: The path to next step is obvious, the expected outcome is stated, and the persona feels moved to proceed.",
            "- **effort_load** — How much cognitive and scanning effort does the persona spend to get oriented?",
            "  - 1: Dense walls of text, unclear hierarchy, or required external research to decipher what is on the page.",
            "  - 3: Scannable but uneven — some sections reward a skim while others demand a full read.",
            "  - 5: One pass tells the persona what they need; effort matches the decision weight.",
            "- **trust_confidence** — Does the page give the persona enough proof and credibility to keep going?",
            "  - 1: No proof, no attribution, no concrete artifacts — claims feel unverifiable.",
            "  - 3: Some trust signals (logo, quote, metric) but none address the persona's specific skepticism.",
            "  - 5: Proof assets speak to the persona's stated pain point, with attribution and specificity.",
            "- **value_communication** — Does the page explain the persona-specific value, not generic benefit?",
            "  - 1: Benefits are generic industry platitudes with no persona fit.",
            "  - 3: Benefits are concrete but not tied to the persona's stated goals or pains.",
            "  - 5: Benefits name the persona's real workflow and show the outcome in their terms.",
            "- **error_recovery** — When something is unclear, missing, or ambiguous, what path back is offered?",
            "  - 1: Dead ends — broken states, empty sections, or confusing CTAs with no recovery cues.",
            "  - 3: Recovery exists but the persona must hunt for it; error copy is generic.",
            "  - 5: Every confusing spot is paired with a clear next action or escape hatch appropriate to the persona.",
            "- **accessibility** — Can the persona's device/ability context consume this page?",
            "  - 1: Blockers for the stated device_context (e.g., unreadable on mobile, tiny touch targets, missing captions).",
            "  - 3: Usable with effort on the stated device; some a11y concerns (contrast, labels, keyboard path).",
            "  - 5: Smooth on the stated device; visible care for contrast, labels, and assistive tech; no blockers.",
            "- **emotional_fit** — Does the tone match the persona's voice and decision style?",
            "  - 1: Tone clashes with the persona (overly hyped for a skeptic, overly technical for a non-dev, etc.).",
            "  - 3: Tone is neutral/safe but does not resonate with the persona's anchors.",
            "  - 5: Copy and visual rhythm feel written FOR this persona's voice and decision style.",
            "If observable evidence is insufficient to place a dimension on this rubric, say so in `reason` and score 3 with a confidence note — do not inflate or guess.",
            "",
            "## Voice Check (do not skip)",
            (
                f"Every persona_voice and persona_reason field MUST be a first-person quote from {persona.name} "
                f"that uses at least one of these anchors: {', '.join(persona.voice[:5])}. "
                "Auditor-voice sentences (impersonal, textbook-UX phrasing) must be rewritten in the persona's voice before finalizing."
            ),
            "",
            "## Execution Instructions",
            "1. Anchor EVERY finding and recommendation to the user's STATED business goal, persona, and core journey. This is the only frame of reference.",
            "2. Stay inside the defined persona.",
            "3. Review only the public pre-login experience unless the provided evidence explicitly includes more.",
            "4. Evaluate the service through the landing-to-onboarding-decision journey, stage by stage.",
            "5. Capture what the persona understands in the first few seconds, what remains vague, what slows momentum, and what increases or decreases trust.",
            "6. Be explicit about whether the site answers these questions well:",
            "   - What is this product?",
            "   - Who is it for?",
            "   - Why should I trust it?",
            "   - Why should I start onboarding now?",
            "7. EVALUATE, do not EXPAND. If the website has content, your job is to judge whether it serves the stated goals — NOT to suggest ways to make that content bigger/prettier/more detailed just because it exists.",
            "8. If you find content that does NOT serve the stated business goal or persona (low-priority features, off-topic sections, distractions), recommend REMOVING, de-emphasizing, or hiding it — NOT expanding it.",
            "9. Before writing any recommendation, ask yourself: 'Does this help the stated business goal or persona journey? If not, delete the recommendation.'",
            "10. Do NOT recommend building new sections/features just because you noticed a mention on the page. Only recommend additions when there is a clear GAP against the stated goals.",
            "11. Distinguish clearly between: direct observation, reasonable inference, recommendation.",
            "12. If the brief lacks enough evidence, call that out directly instead of inventing certainty.",
            "13. Add strengths as well as weaknesses.",
            "14. Severity rubric — assign each finding exactly one priority using these behavioral anchors. Do NOT use 'High' as a default; most findings are Medium unless they meet the specific tests below.",
            "    - Blocker: the persona cannot complete the stated core_journey without external help (the journey is fundamentally broken for this persona, e.g., required CTA is missing, page fails to load critical content, required step is impossible).",
            "    - High: the persona completes the journey but with friction that directly threatens the stated business_goal (activation/conversion/trust is materially at risk for the stated persona and goal, not generic UX).",
            "    - Medium: the persona completes the journey with avoidable effort, confusion, or missed opportunity, but no direct business_goal threat.",
            "    - Nit: polish, consistency, or edge-case issue with no journey impact.",
            "    Each finding's impact_on_user + impact_on_business MUST justify the chosen priority by addressing Nielsen's severity triad: frequency of occurrence, magnitude of impact on the persona, and persistence (does the problem compound across attempts or is it a one-time speed bump). If the justification does not establish all three, downgrade.",
            "15. Every finding should explain why it matters for the stated business goal and persona journey — not generic UX principles.",
            "16. Finish with prioritized improvements grouped into quick wins, structural fixes, and validation experiments.",
            "17. Return JSON matching the required output schema.",
            "",
            "## Reflection Loop",
            "Before finalizing, self-check against:",
            criteria_lines,
            "- the review is explicitly useful for improving the public landing-to-onboarding conversion path",
            "- the review explains whether the visitor has a compelling reason to log in or sign up now",
            "- EVERY recommendation is tied to the stated business goal or persona — none are just 'enhance this existing content because I saw it on the page'",
            "- NO recommendation suggests expanding content that is unrelated to the stated business priorities",
            "- If the page has off-topic or low-priority content (compared to the stated goal), the review recommends removing/de-emphasizing it rather than expanding it",
            "- Severity discipline: at most one Blocker per 5 findings unless the journey is genuinely broken. If every finding is High, downgrade the weakest. If the journey works cleanly, it is correct and expected for the review to contain only Medium/Nit findings — do not invent High/Blocker to add urgency.",
            "- Each finding's impact_on_user and impact_on_business together reconstruct Nielsen's severity triad (frequency, magnitude, persistence); if the triad is not visible in the text, revise the finding before finalizing.",
            "- Voice audit: re-read every persona_voice and persona_reason field — if any sentence could plausibly appear in a generic UX audit report, rewrite it in first-person and use at least one of the persona voice anchors above.",
            "",
            "If any item fails, revise before returning the final result.",
            "",
            "## Required Output",
            "Return a single JSON object with these top-level keys: review_summary, persona_card, scores, strengths, findings, prioritized_improvements, open_questions. Each score is `{reason, score}`; each finding includes priority, journey_stage, problem, persona_voice, evidence, impact_on_user, impact_on_business, improvement_direction. Structural contracts are enforced via the API's responseSchema on the inline and fallback call paths.",
        ]
    )

    return ReviewPacket(
        markdown=markdown,
        output_skeleton=schema,
        response_json_schema=build_response_json_schema(schema),
    )
