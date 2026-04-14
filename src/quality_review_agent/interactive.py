from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .markdown_report import render_markdown_report
from .service import create_brief_from_form, generate_persona_from_form, run_review_for_brief


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def _prompt(question: str, default: str = "", required: bool = True) -> str:
    hint = f" [{default}]" if default else (" (선택)" if not required else "")
    while True:
        try:
            answer = input(f"  {question}{hint}\n  > ").strip()
        except EOFError:
            answer = ""
        if not answer and default:
            return default
        if answer:
            return answer
        if not required:
            return ""
        _print("  ⚠️  값을 입력해주세요.\n")


def _confirm(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"  {question} {suffix}\n  > ").strip().lower()
        except EOFError:
            answer = ""
        if not answer:
            return default
        if answer in {"y", "yes", "예", "네"}:
            return True
        if answer in {"n", "no", "아니오", "아니요"}:
            return False


def _format_persona(persona: dict) -> str:
    lines = []
    lines.append("\n" + "━" * 60)
    lines.append(f"  👤 {persona.get('name', 'Target User')}")
    lines.append(f"     {persona.get('segment', '')}")
    lines.append("━" * 60)
    if persona.get("job_to_be_done"):
        lines.append(f"  Job to be done: {persona['job_to_be_done']}")
    if persona.get("context"):
        lines.append(f"  맥락          : {persona['context']}")
    if persona.get("success_definition"):
        lines.append(f"  성공 정의     : {persona['success_definition']}")
    if persona.get("decision_style"):
        lines.append(f"  의사결정      : {persona['decision_style']}")
    if persona.get("technical_level"):
        lines.append(f"  기술 수준     : {persona['technical_level']}")
    if persona.get("device_context"):
        lines.append(f"  주 사용 기기  : {persona['device_context']}")
    if persona.get("goals"):
        lines.append("  목표:")
        for g in persona["goals"]:
            lines.append(f"    - {g}")
    if persona.get("pain_points"):
        lines.append("  불편 (Pain points):")
        for p in persona["pain_points"]:
            lines.append(f"    - {p}")
    if persona.get("voice"):
        lines.append(f"  목소리/태도   : {', '.join(persona['voice'])}")
    lines.append("━" * 60 + "\n")
    return "\n".join(lines)


def run_interactive(url: str = "", output_dir: Path | None = None, model: str = "gemini-2.5-pro") -> int:
    _print("\n╔" + "═" * 58 + "╗")
    _print("║  🔍 Quality Review Agent — 대화형 리뷰                   ║")
    _print("╚" + "═" * 58 + "╝\n")

    if not url:
        url = _prompt("리뷰할 서비스 URL이 무엇인가요?", required=True)

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        _print(f"\n❌ 유효한 URL이 아닙니다: {url}")
        return 1

    default_name = parsed.netloc.replace("www.", "").split(".")[0].title()

    _print("\n📝 몇 가지 질문을 드릴게요. 선택 항목은 비워두셔도 됩니다.\n")

    service_name = _prompt("서비스 이름", default=default_name)
    service_type = _prompt("서비스 유형 (예: SaaS, 커머스, 랜딩페이지)", default="web product")
    core_journey = _prompt("가장 중요한 사용자 행동은? (예: 회원가입 후 온보딩 시작)")
    persona_description = _prompt("주요 사용자는 누구인가요? (예: 패션에 관심 많은 20-30대 여성)")
    business_goal = _prompt("비즈니스 목표 (선택)", required=False)
    problems = _prompt("알려진 사용자 문제/VOC — 한 줄에 하나, 여러 개는 쉼표 구분 (선택)", required=False)
    competitors = _prompt("경쟁 제품이나 대안 도구 — 쉼표 구분 (선택)", required=False)

    form = {
        "service_name": service_name,
        "service_url": url,
        "service_type": service_type,
        "core_journey": core_journey,
        "persona_description": persona_description,
        "business_goal": business_goal,
        "problems": problems,
        "competitors": competitors,
        "model": model,
    }

    # Step 1: Persona enrichment
    _print("\n🧠 AI가 페르소나를 분석하고 있습니다...\n")
    try:
        persona = generate_persona_from_form(form, model=model)
    except Exception as exc:
        _print(f"\n❌ 페르소나 생성 실패: {exc}")
        return 2

    while True:
        _print(_format_persona(persona))
        if _confirm("이 페르소나로 리뷰를 진행할까요?", default=True):
            break
        if _confirm("다시 생성할까요? (아니오면 종료)", default=True):
            _print("\n🔄 다시 생성 중...\n")
            try:
                persona = generate_persona_from_form(form, model=model)
            except Exception as exc:
                _print(f"\n❌ 재생성 실패: {exc}")
                return 2
        else:
            _print("\n중단되었습니다.")
            return 0

    # Step 2: Run review
    _print("\n🚀 리뷰 생성 중 — 최대 1분 정도 걸릴 수 있습니다...\n")
    build_dir = Path("build/web")
    build_dir.mkdir(parents=True, exist_ok=True)
    try:
        brief = create_brief_from_form(form, model=model, persona_override=persona)
        result = run_review_for_brief(
            brief=brief,
            schema_path=Path("review-output-schema.json"),
            model=model,
            packet_output=build_dir / "review-packet.md",
            skeleton_output=build_dir / "output-skeleton.json",
            result_output=build_dir / "review-result.json",
            raw_output=build_dir / "gemini-raw-response.json",
        )
    except Exception as exc:
        _print(f"\n❌ 리뷰 실행 실패: {exc}")
        return 3

    # Step 3: Save markdown report
    output_dir = output_dir or Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in service_name.lower())
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    md_path = output_dir / f"review-{safe_name}-{timestamp}.md"

    md_content = render_markdown_report(service_name, url, persona, result)
    md_path.write_text(md_content, encoding="utf-8")

    _print(f"\n✅ 완료! 리뷰 리포트가 저장되었습니다:\n   {md_path}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="quality_review_agent interactive")
    parser.add_argument("url", nargs="?", default="", help="Service URL to review")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for the markdown report (default: cwd)")
    parser.add_argument("--model", default="gemini-2.5-pro", help="Gemini model to use")
    args = parser.parse_args(argv)
    return run_interactive(url=args.url, output_dir=args.output_dir, model=args.model)


if __name__ == "__main__":
    sys.exit(main())
