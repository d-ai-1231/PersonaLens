from __future__ import annotations

from datetime import datetime
from typing import Any


SCORE_LABELS = {
    "task_clarity": "Task clarity",
    "task_success": "Task success",
    "effort_load": "Effort load",
    "trust_confidence": "Trust & confidence",
    "value_communication": "Value communication",
    "error_recovery": "Error recovery",
    "accessibility": "Accessibility",
    "emotional_fit": "Emotional fit",
}

PRIORITY_EMOJI = {
    "Blocker": "🚨",
    "High": "🔴",
    "Medium": "🟡",
    "Nit": "⚪",
}


def render_markdown_report(service_name: str, service_url: str, persona: dict, result: dict) -> str:
    summary = result.get("review_summary") or {}
    scores = result.get("scores") or {}
    strengths = result.get("strengths") or []
    findings = result.get("findings") or []
    improvements = result.get("prioritized_improvements") or {}
    open_questions = result.get("open_questions") or []

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines: list[str] = []
    lines.append(f"# {service_name} — Quality Review Report")
    lines.append("")
    lines.append(f"- **Service URL**: {service_url}")
    lines.append(f"- **Generated at**: {now}")
    lines.append(f"- **Confidence**: {summary.get('confidence', '-')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary
    lines.append("## 📋 Summary")
    lines.append("")
    if summary.get("verdict"):
        lines.append(f"**Verdict**: {summary['verdict']}")
        lines.append("")
    if summary.get("first_impression"):
        lines.append(f"**First impression**: {summary['first_impression']}")
        lines.append("")
    if summary.get("why_it_matters"):
        lines.append(f"**Why it matters**: {summary['why_it_matters']}")
        lines.append("")

    # Persona
    lines.append("## 👤 Target Persona")
    lines.append("")
    lines.append(f"**{persona.get('name', 'Target User')}** — {persona.get('segment', '')}")
    lines.append("")
    if persona.get("job_to_be_done"):
        lines.append(f"- **Job to be done**: {persona['job_to_be_done']}")
    if persona.get("context"):
        lines.append(f"- **Context**: {persona['context']}")
    if persona.get("success_definition"):
        lines.append(f"- **Success definition**: {persona['success_definition']}")
    if persona.get("decision_style"):
        lines.append(f"- **Decision style**: {persona['decision_style']}")
    lines.append("")
    if persona.get("goals"):
        lines.append("**Goals:**")
        for g in persona["goals"]:
            lines.append(f"- {g}")
        lines.append("")
    if persona.get("pain_points"):
        lines.append("**Pain points:**")
        for p in persona["pain_points"]:
            lines.append(f"- {p}")
        lines.append("")

    # Scores
    lines.append("## 📊 Scores")
    lines.append("")
    lines.append("| Dimension | Score | Reason |")
    lines.append("| --- | --- | --- |")
    for key, payload in scores.items():
        if not isinstance(payload, dict):
            continue
        label = SCORE_LABELS.get(key, key.replace("_", " ").title())
        score = payload.get("score", "-")
        reason = (payload.get("reason") or "").replace("|", "\\|")
        lines.append(f"| {label} | {score}/5 | {reason} |")
    lines.append("")

    # Strengths
    if strengths:
        lines.append("## ✅ Strengths")
        lines.append("")
        for item in strengths:
            title = item.get("title", "Untitled")
            stage = item.get("journey_stage", "")
            reason = item.get("persona_reason", "")
            evidence = item.get("evidence", "")
            lines.append(f"### {title}")
            if stage:
                lines.append(f"*Stage: {stage}*")
                lines.append("")
            if reason:
                lines.append(f"- **User perspective**: {reason}")
            if evidence:
                lines.append(f"- **Evidence**: {evidence}")
            lines.append("")

    # Findings
    if findings:
        lines.append("## 🔍 Findings")
        lines.append("")
        for item in findings:
            priority = item.get("priority", "Info")
            emoji = PRIORITY_EMOJI.get(priority, "•")
            title = item.get("title", "Untitled")
            lines.append(f"### {emoji} [{priority}] {title}")
            lines.append("")
            if item.get("journey_stage"):
                lines.append(f"*Stage: {item['journey_stage']}*")
                lines.append("")
            if item.get("problem"):
                lines.append(f"- **Problem**: {item['problem']}")
            if item.get("persona_voice"):
                lines.append(f"- **Persona voice**: \"{item['persona_voice']}\"")
            if item.get("evidence"):
                lines.append(f"- **Evidence**: {item['evidence']}")
            if item.get("impact_on_user"):
                lines.append(f"- **User impact**: {item['impact_on_user']}")
            if item.get("impact_on_business"):
                lines.append(f"- **Business impact**: {item['impact_on_business']}")
            if item.get("improvement_direction"):
                lines.append(f"- **Improvement direction**: {item['improvement_direction']}")
            lines.append("")

    # Improvements
    lines.append("## 🚀 Improvements")
    lines.append("")

    def render_improvement_group(title: str, items: list[dict], change_key: str = "change") -> None:
        if not items:
            return
        lines.append(f"### {title}")
        lines.append("")
        for item in items:
            change = item.get(change_key) or item.get("experiment") or "Untitled"
            lines.append(f"#### {change}")
            if item.get("expected_user_outcome") or item.get("hypothesis"):
                lines.append(f"- **User outcome**: {item.get('expected_user_outcome') or item.get('hypothesis')}")
            if item.get("expected_business_outcome") or item.get("success_metric"):
                lines.append(f"- **Business outcome**: {item.get('expected_business_outcome') or item.get('success_metric')}")
            if item.get("estimated_effort"):
                lines.append(f"- **Estimated effort**: {item['estimated_effort']}")
            lines.append("")

    render_improvement_group("⚡ Quick wins", improvements.get("quick_wins") or [])
    render_improvement_group("🔧 Structural fixes", improvements.get("structural_fixes") or [])
    render_improvement_group("🧪 Validation experiments", improvements.get("validation_experiments") or [], change_key="experiment")

    # Open questions
    if open_questions:
        lines.append("## ❓ Open questions")
        lines.append("")
        for q in open_questions:
            lines.append(f"- {q}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Generated by PersonaLens.*")
    lines.append("")

    return "\n".join(lines)
