"""Helper script for Claude Code skill integration.

Usage:
  python -m quality_review_agent.skill_helper persona <form.json>
    → Outputs enriched persona JSON to stdout

  python -m quality_review_agent.skill_helper review <form.json> <persona.json> <output.md>
    → Runs review with the confirmed persona, writes markdown to output.md
    → Prints summary JSON to stdout
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from .markdown_report import render_markdown_report
from .service import create_brief_from_form, generate_persona_from_form, run_review_for_brief


def cmd_persona(form_path: Path) -> int:
    form = json.loads(form_path.read_text(encoding="utf-8"))
    persona = generate_persona_from_form(form, model=form.get("model", "gemini-2.5-pro"))
    print(json.dumps(persona, ensure_ascii=False, indent=2))
    return 0


def cmd_review(form_path: Path, persona_path: Path, output_md: Path) -> int:
    form = json.loads(form_path.read_text(encoding="utf-8"))
    persona = json.loads(persona_path.read_text(encoding="utf-8"))

    build_dir = Path("build/skill")
    build_dir.mkdir(parents=True, exist_ok=True)

    brief = create_brief_from_form(form, model=form.get("model", "gemini-2.5-pro"), persona_override=persona)
    result = run_review_for_brief(
        brief=brief,
        schema_path=Path("review-output-schema.json"),
        model=form.get("model", "gemini-2.5-pro"),
        packet_output=build_dir / "review-packet.md",
        skeleton_output=build_dir / "output-skeleton.json",
        result_output=build_dir / "review-result.json",
        raw_output=build_dir / "gemini-raw-response.json",
    )

    md = render_markdown_report(
        service_name=form.get("service_name", "Service"),
        service_url=form.get("service_url", ""),
        persona=persona,
        result=result,
    )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(md, encoding="utf-8")

    summary = {
        "status": "ok",
        "markdown_path": str(output_md.resolve()),
        "service_name": form.get("service_name"),
        "verdict": (result.get("review_summary") or {}).get("verdict"),
        "confidence": (result.get("review_summary") or {}).get("confidence"),
        "finding_count": len(result.get("findings") or []),
        "strength_count": len(result.get("strengths") or []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: skill_helper <persona|review> ...", file=sys.stderr)
        return 1

    command = argv[0]
    if command == "persona":
        if len(argv) != 2:
            print("Usage: skill_helper persona <form.json>", file=sys.stderr)
            return 1
        return cmd_persona(Path(argv[1]))

    if command == "review":
        if len(argv) != 4:
            print("Usage: skill_helper review <form.json> <persona.json> <output.md>", file=sys.stderr)
            return 1
        return cmd_review(Path(argv[1]), Path(argv[2]), Path(argv[3]))

    print(f"Unknown command: {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
