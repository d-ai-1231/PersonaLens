from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .diagnostics import format_gemini_error, format_unexpected_error
from .markdown_report import render_markdown_report
from .service import create_brief_from_form, generate_persona_from_form, run_review_for_brief


def _print(msg: str = "") -> None:
    print(msg, flush=True)


def _prompt(question: str, default: str = "", required: bool = True) -> str:
    hint = f" [{default}]" if default else (" (optional)" if not required else "")
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
        _print("  ⚠️  Please enter a value.\n")


def _confirm(question: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"  {question} {suffix}\n  > ").strip().lower()
        except EOFError:
            answer = ""
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False


def _format_persona(persona: dict) -> str:
    lines = []
    lines.append("\n" + "━" * 60)
    lines.append(f"  👤 {persona.get('name', 'Target User')}")
    lines.append(f"     {persona.get('segment', '')}")
    lines.append("━" * 60)
    if persona.get("job_to_be_done"):
        lines.append(f"  Job to be done   : {persona['job_to_be_done']}")
    if persona.get("context"):
        lines.append(f"  Context          : {persona['context']}")
    if persona.get("success_definition"):
        lines.append(f"  Success def.     : {persona['success_definition']}")
    if persona.get("decision_style"):
        lines.append(f"  Decision style   : {persona['decision_style']}")
    if persona.get("technical_level"):
        lines.append(f"  Tech level       : {persona['technical_level']}")
    if persona.get("device_context"):
        lines.append(f"  Device           : {persona['device_context']}")
    if persona.get("goals"):
        lines.append("  Goals:")
        for g in persona["goals"]:
            lines.append(f"    - {g}")
    if persona.get("pain_points"):
        lines.append("  Pain points:")
        for p in persona["pain_points"]:
            lines.append(f"    - {p}")
    if persona.get("voice"):
        lines.append(f"  Voice / tone     : {', '.join(persona['voice'])}")
    lines.append("━" * 60 + "\n")
    return "\n".join(lines)


def run_interactive(url: str = "", output_dir: Path | None = None, model: str = "gemini-2.5-pro") -> int:
    _print("\n╔" + "═" * 58 + "╗")
    _print("║  🔍 PersonaLens — Interactive Review             ║")
    _print("╚" + "═" * 58 + "╝\n")

    if not url:
        url = _prompt("What is the service URL?", required=True)

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        _print(f"\n❌ Invalid URL: {url}")
        return 1

    default_name = parsed.netloc.replace("www.", "").split(".")[0].title()

    _print("\n📝 I'll ask a few questions. Optional fields can be left blank.\n")

    service_name = _prompt("Service name", default=default_name)
    service_type = _prompt("Service type (e.g., SaaS, e-commerce, landing page)", default="web product")
    core_journey = _prompt("Most important user action (e.g., sign up and start onboarding)")
    persona_description = _prompt("Who is the main user? (e.g., developers who want to boost productivity)")
    business_goal = _prompt("Business goal", required=False)
    problems = _prompt("Known user problems or VOC — comma-separated", required=False)
    competitors = _prompt("Real competitors or alternatives — comma-separated", required=False)

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
    _print("\n🧠 Analyzing the persona...\n")
    try:
        persona = generate_persona_from_form(form, model=model)
    except Exception as exc:
        _print(f"\n❌ {format_unexpected_error(str(exc), 'generating persona')}")
        return 2

    while True:
        _print(_format_persona(persona))
        if _confirm("Run the review with this persona?", default=True):
            break
        if _confirm("Regenerate? (no will exit)", default=True):
            _print("\n🔄 Regenerating...\n")
            try:
                persona = generate_persona_from_form(form, model=model)
            except Exception as exc:
                _print(f"\n❌ {format_unexpected_error(str(exc), 'regenerating persona')}")
                return 2
        else:
            _print("\nAborted.")
            return 0

    # Step 2: Run review
    _print("\n🚀 Generating the review — this may take up to a minute...\n")
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
    except GeminiError as exc:
        _print(f"\n❌ {format_gemini_error(str(exc))}")
        return 3
    except Exception as exc:
        _print(f"\n❌ {format_unexpected_error(str(exc), 'running review')}")
        return 3

    # Step 3: Save markdown report
    output_dir = output_dir or Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in service_name.lower())
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    md_path = output_dir / f"review-{safe_name}-{timestamp}.md"

    md_content = render_markdown_report(service_name, url, persona, result)
    md_path.write_text(md_content, encoding="utf-8")

    _print(f"\n✅ Done! Review report saved to:\n   {md_path}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="personalens interactive")
    parser.add_argument("url", nargs="?", default="", help="Service URL to review")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for the markdown report (default: cwd)")
    parser.add_argument("--model", default="gemini-2.5-pro", help="Gemini model to use")
    args = parser.parse_args(argv)
    return run_interactive(url=args.url, output_dir=args.output_dir, model=args.model)


if __name__ == "__main__":
    sys.exit(main())
