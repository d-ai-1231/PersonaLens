from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .agent import build_review_packet, load_schema
from .gemini import GeminiConfig, GeminiError, enrich_persona, run_review
from .models import Persona, ReviewBrief, Service
from .webpage import fetch_webpage_context


def load_brief(input_path: Path) -> ReviewBrief:
    return ReviewBrief.from_dict(json.loads(input_path.read_text(encoding="utf-8")))


def build_packet_for_brief(brief: ReviewBrief, schema_path: Path, model: str = "gemini-2.5-pro"):
    webpage_context = fetch_webpage_context(brief.service.url)
    schema = load_schema(schema_path)
    return build_review_packet(brief, schema, webpage_context=webpage_context), webpage_context


def run_review_for_brief(
    brief: ReviewBrief,
    schema_path: Path,
    model: str,
    packet_output: Path,
    skeleton_output: Path,
    result_output: Path,
    raw_output: Path,
) -> dict:
    packet, _webpage_context = build_packet_for_brief(brief, schema_path, model=model)

    packet_output.parent.mkdir(parents=True, exist_ok=True)
    skeleton_output.parent.mkdir(parents=True, exist_ok=True)
    result_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.parent.mkdir(parents=True, exist_ok=True)

    packet_output.write_text(packet.markdown + "\n", encoding="utf-8")
    skeleton_output.write_text(
        json.dumps(packet.output_skeleton, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = run_review(
        packet_markdown=packet.markdown,
        schema=packet.response_json_schema,
        config=GeminiConfig(model=model),
        raw_output_path=raw_output,
    )

    result_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _parse_form_basics(data: dict[str, str]) -> dict:
    """Extract and normalize basic fields from the form."""
    service_name = normalize_user_text(data["service_name"])
    service_url = normalize_url_text(data["service_url"])
    core_journey = normalize_user_text(data["core_journey"])
    persona_description = normalize_user_text(data["persona_description"])
    problem_text = normalize_user_text(data.get("problems", ""))
    business_goal = normalize_user_text(data["business_goal"]) or "Improve activation and reduce drop-off in the primary journey."
    service_type = normalize_user_text(data["service_type"]) or "web product"
    competitors_raw = normalize_user_text(data.get("competitors", ""))
    competitors = [c.strip() for c in competitors_raw.replace("\n", ",").split(",") if c.strip()]

    problem_lines = [line.strip(" -") for line in problem_text.splitlines() if line.strip()]
    if not problem_lines:
        problem_lines = [item.strip() for item in problem_text.split(",") if item.strip()]

    return {
        "service_name": service_name,
        "service_url": service_url,
        "core_journey": core_journey,
        "persona_description": persona_description,
        "business_goal": business_goal,
        "service_type": service_type,
        "competitors": competitors,
        "problem_lines": problem_lines,
    }


def generate_persona_from_form(data: dict[str, str], model: str = "gemini-2.5-pro") -> dict:
    """Step 1: Generate an enriched persona card from form input.
    Returns a dict suitable for display and serialization."""
    basics = _parse_form_basics(data)
    webpage_context = fetch_webpage_context(basics["service_url"])

    try:
        enriched = enrich_persona(
            service_name=basics["service_name"],
            service_url=basics["service_url"],
            service_type=basics["service_type"],
            core_journey=basics["core_journey"],
            persona_description=basics["persona_description"],
            problems=basics["problem_lines"],
            business_goal=basics["business_goal"],
            webpage_text=webpage_context,
            config=GeminiConfig(model=model),
        )
        persona_dict = {
            "name": enriched.get("name", "Target User"),
            "segment": enriched.get("segment", basics["persona_description"]),
            "job_to_be_done": enriched.get("job_to_be_done", f"Understand whether {basics['service_name']} solves my problem"),
            "context": enriched.get("context", "Arrives with limited time and high expectations"),
            "goals": enriched.get("goals", ["Understand the product value"])[:3],
            "pain_points": enriched.get("pain_points", basics["problem_lines"] or ["Unclear value"])[:3],
            "technical_level": enriched.get("technical_level", "medium"),
            "decision_style": enriched.get("decision_style", "trust-driven"),
            "device_context": enriched.get("device_context", "desktop"),
            "access_needs": enriched.get("access_needs", ["Clear language"])[:3],
            "success_definition": enriched.get("success_definition", f"I understand what {basics['service_name']} does and feel confident to start"),
            "voice": enriched.get("voice", ["practical", "time-conscious", "skeptical", "low-hype"])[:5],
            "evidence_sources": enriched.get("evidence_sources", ["user description", "website snapshot"])[:3],
            "confidence": enriched.get("confidence", "medium"),
        }
    except (GeminiError, json.JSONDecodeError, OSError, ValueError, TypeError):
        persona_dict = {
            "name": "Target User",
            "segment": basics["persona_description"],
            "job_to_be_done": f"Understand whether {basics['service_name']} solves my problem and start using it",
            "context": "Arrives with limited time and will leave quickly if value is unclear",
            "goals": ["Understand the product value quickly", "Complete the core journey", "Feel confident to continue"],
            "pain_points": basics["problem_lines"][:3] or ["Unclear product value"],
            "technical_level": infer_technical_level(basics["persona_description"]),
            "decision_style": "trust-driven",
            "device_context": "desktop",
            "access_needs": ["Clear value explanation", "Low ambiguity in action path"],
            "success_definition": f"I understand what {basics['service_name']} does and can take the next step confidently",
            "voice": infer_voice_anchors(basics["persona_description"], basics["problem_lines"]),
            "evidence_sources": ["user description", "problem statements", "website snapshot"],
            "confidence": "medium",
        }
    return persona_dict


def create_brief_from_form(data: dict[str, str], model: str = "gemini-2.5-pro", persona_override: dict | None = None) -> ReviewBrief:
    basics = _parse_form_basics(data)

    if persona_override is not None:
        persona_dict = persona_override
    else:
        persona_dict = generate_persona_from_form(data, model=model)

    persona = Persona(
        name=persona_dict.get("name", "Target User"),
        segment=persona_dict.get("segment", basics["persona_description"]),
        job_to_be_done=persona_dict.get("job_to_be_done", ""),
        context=persona_dict.get("context", ""),
        goals=persona_dict.get("goals", [])[:5],
        pain_points=persona_dict.get("pain_points", [])[:5],
        technical_level=persona_dict.get("technical_level", "medium"),
        decision_style=persona_dict.get("decision_style", "trust-driven"),
        device_context=persona_dict.get("device_context", "desktop"),
        access_needs=persona_dict.get("access_needs", [])[:5],
        success_definition=persona_dict.get("success_definition", ""),
        voice=persona_dict.get("voice", ["practical", "skeptical", "low-hype"])[:5],
        evidence_sources=persona_dict.get("evidence_sources", ["user description"])[:3],
        confidence=persona_dict.get("confidence", "medium"),
    )

    return ReviewBrief(
        service=Service(name=basics["service_name"], url=basics["service_url"], type=basics["service_type"]),
        review_goal=f"Evaluate whether the target user can complete this journey with clarity, trust, and momentum: {basics['core_journey']}",
        core_journey=basics["core_journey"],
        business_goal=basics["business_goal"],
        persona=persona,
        evidence=[f"Known user problem: {p}" for p in basics["problem_lines"][:3]],
        known_constraints=[
            "Prioritize clarity, trust, and completion issues.",
            "Do not turn findings into pixel-level prescriptions.",
            "If evidence is weak, state that clearly in the output.",
        ],
        notes=[
            "Keep the review understandable to non-developers.",
            "Separate observation, inference, and recommendation.",
            "Every recommendation must explain user impact and business impact.",
        ],
        competitors=basics["competitors"],
    )


def review_brief_to_json(brief: ReviewBrief) -> str:
    return json.dumps(asdict(brief), ensure_ascii=False, indent=2)


def infer_voice_anchors(persona_description: str, problem_lines: list[str]) -> list[str]:
    text = f"{persona_description} {' '.join(problem_lines)}".lower()
    anchors = ["practical", "time-conscious"]

    if any(word in text for word in ["developer", "engineer", "technical"]):
        anchors.append("skeptical")
    if any(word in text for word in ["trust", "uncertain", "not sure", "모르", "의심"]):
        anchors.append("risk-aware")
    if any(word in text for word in ["fast", "quick", "time", "busy", "빨리"]):
        anchors.append("results-oriented")

    while len(anchors) < 4:
        anchors.append("low-hype")
    return anchors[:5]


def infer_technical_level(persona_description: str) -> str:
    text = persona_description.lower()
    if any(word in text for word in ["developer", "engineer", "programmer", "dev"]):
        return "high"
    if any(word in text for word in ["marketer", "founder", "manager", "operator"]):
        return "medium"
    return "low"


def normalize_user_text(value: str) -> str:
    return (
        value.strip()
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


def normalize_url_text(value: str) -> str:
    normalized = normalize_user_text(value).strip()
    return normalized.strip("\"'")
