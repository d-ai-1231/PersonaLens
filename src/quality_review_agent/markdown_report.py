from __future__ import annotations

from datetime import datetime
from typing import Any


SCORE_LABELS_KO = {
    "task_clarity": "작업 명확성",
    "task_success": "작업 완수도",
    "effort_load": "노력 부담",
    "trust_confidence": "신뢰 확신",
    "value_communication": "가치 전달력",
    "error_recovery": "오류 복구",
    "accessibility": "접근성",
    "emotional_fit": "감성 적합도",
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
    lines.append(f"# {service_name} — 품질 리뷰 리포트")
    lines.append("")
    lines.append(f"- **서비스 URL**: {service_url}")
    lines.append(f"- **생성 시각**: {now}")
    lines.append(f"- **신뢰도**: {summary.get('confidence', '-')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary
    lines.append("## 📋 요약")
    lines.append("")
    if summary.get("verdict"):
        lines.append(f"**판정**: {summary['verdict']}")
        lines.append("")
    if summary.get("first_impression"):
        lines.append(f"**첫인상**: {summary['first_impression']}")
        lines.append("")
    if summary.get("why_it_matters"):
        lines.append(f"**왜 중요한가**: {summary['why_it_matters']}")
        lines.append("")

    # Persona
    lines.append("## 👤 타겟 페르소나")
    lines.append("")
    lines.append(f"**{persona.get('name', 'Target User')}** — {persona.get('segment', '')}")
    lines.append("")
    if persona.get("job_to_be_done"):
        lines.append(f"- **Job to be done**: {persona['job_to_be_done']}")
    if persona.get("context"):
        lines.append(f"- **맥락**: {persona['context']}")
    if persona.get("success_definition"):
        lines.append(f"- **성공 정의**: {persona['success_definition']}")
    if persona.get("decision_style"):
        lines.append(f"- **의사결정 스타일**: {persona['decision_style']}")
    lines.append("")
    if persona.get("goals"):
        lines.append("**목표:**")
        for g in persona["goals"]:
            lines.append(f"- {g}")
        lines.append("")
    if persona.get("pain_points"):
        lines.append("**불편:**")
        for p in persona["pain_points"]:
            lines.append(f"- {p}")
        lines.append("")

    # Scores
    lines.append("## 📊 평가 점수")
    lines.append("")
    lines.append("| 항목 | 점수 | 사유 |")
    lines.append("| --- | --- | --- |")
    for key, payload in scores.items():
        if not isinstance(payload, dict):
            continue
        label = SCORE_LABELS_KO.get(key, key.replace("_", " "))
        score = payload.get("score", "-")
        reason = (payload.get("reason") or "").replace("|", "\\|")
        lines.append(f"| {label} | {score}/5 | {reason} |")
    lines.append("")

    # Strengths
    if strengths:
        lines.append("## ✅ 강점")
        lines.append("")
        for item in strengths:
            title = item.get("title", "Untitled")
            stage = item.get("journey_stage", "")
            reason = item.get("persona_reason", "")
            evidence = item.get("evidence", "")
            lines.append(f"### {title}")
            if stage:
                lines.append(f"*단계: {stage}*")
                lines.append("")
            if reason:
                lines.append(f"- **사용자 관점**: {reason}")
            if evidence:
                lines.append(f"- **근거**: {evidence}")
            lines.append("")

    # Findings
    if findings:
        lines.append("## 🔍 발견 사항")
        lines.append("")
        for item in findings:
            priority = item.get("priority", "Info")
            emoji = PRIORITY_EMOJI.get(priority, "•")
            title = item.get("title", "Untitled")
            lines.append(f"### {emoji} [{priority}] {title}")
            lines.append("")
            if item.get("journey_stage"):
                lines.append(f"*단계: {item['journey_stage']}*")
                lines.append("")
            if item.get("problem"):
                lines.append(f"- **문제**: {item['problem']}")
            if item.get("persona_voice"):
                lines.append(f"- **사용자 목소리**: \"{item['persona_voice']}\"")
            if item.get("evidence"):
                lines.append(f"- **근거**: {item['evidence']}")
            if item.get("impact_on_user"):
                lines.append(f"- **사용자 영향**: {item['impact_on_user']}")
            if item.get("impact_on_business"):
                lines.append(f"- **비즈니스 영향**: {item['impact_on_business']}")
            if item.get("improvement_direction"):
                lines.append(f"- **개선 방향**: {item['improvement_direction']}")
            lines.append("")

    # Improvements
    lines.append("## 🚀 개선 제안")
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
                lines.append(f"- **사용자 성과**: {item.get('expected_user_outcome') or item.get('hypothesis')}")
            if item.get("expected_business_outcome") or item.get("success_metric"):
                lines.append(f"- **비즈니스 성과**: {item.get('expected_business_outcome') or item.get('success_metric')}")
            if item.get("estimated_effort"):
                lines.append(f"- **예상 노력**: {item['estimated_effort']}")
            lines.append("")

    render_improvement_group("⚡ 빠른 개선 (Quick Wins)", improvements.get("quick_wins") or [])
    render_improvement_group("🔧 구조적 개선 (Structural Fixes)", improvements.get("structural_fixes") or [])
    render_improvement_group("🧪 검증 실험 (Validation Experiments)", improvements.get("validation_experiments") or [], change_key="experiment")

    # Open questions
    if open_questions:
        lines.append("## ❓ 열린 질문")
        lines.append("")
        for q in open_questions:
            lines.append(f"- {q}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*이 리포트는 Quality Review Agent에 의해 생성되었습니다.*")
    lines.append("")

    return "\n".join(lines)
