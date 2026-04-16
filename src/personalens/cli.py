from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .agent import load_schema
from .diagnostics import format_gemini_error, format_unexpected_error, format_validation_issues
from .gemini import GeminiError
from .models import ValidationError
from .service import build_packet_for_brief, load_brief, run_review_for_brief
from .slack_server import serve_slack_commands


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="personalens")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build a review packet from a brief JSON file")
    build_parser.add_argument("--input", required=True, help="Path to the brief JSON file")
    build_parser.add_argument("--output", required=True, help="Path to the generated markdown packet")
    build_parser.add_argument(
        "--schema",
        default="review-output-schema.json",
        help="Path to the output schema JSON file",
    )
    build_parser.add_argument(
        "--skeleton-output",
        default="build/output-skeleton.json",
        help="Path to write the output skeleton JSON",
    )

    run_parser = subparsers.add_parser("run", help="Run the review agent against Gemini")
    run_parser.add_argument("--input", required=True, help="Path to the brief JSON file")
    run_parser.add_argument("--output", required=True, help="Path to write the model JSON response")
    run_parser.add_argument(
        "--schema",
        default="review-output-schema.json",
        help="Path to the output schema JSON file",
    )
    run_parser.add_argument(
        "--packet-output",
        default="build/review-packet.md",
        help="Path to write the generated markdown packet",
    )
    run_parser.add_argument(
        "--skeleton-output",
        default="build/output-skeleton.json",
        help="Path to write the output skeleton JSON",
    )
    run_parser.add_argument(
        "--model",
        default="gemini-2.5-pro",
        help="Gemini model name",
    )
    run_parser.add_argument(
        "--raw-output",
        default="build/gemini-raw-response.json",
        help="Path to write the raw Gemini API response",
    )

    slack_parser = subparsers.add_parser("slack-serve", help="Run a Slack slash-command bridge server")
    slack_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the Slack bridge server",
    )
    slack_parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="Port to bind the Slack bridge server",
    )
    slack_parser.add_argument(
        "--signing-secret-env",
        default="SLACK_SIGNING_SECRET",
        help="Environment variable containing the Slack signing secret",
    )
    slack_parser.add_argument(
        "--default-model",
        default="gemini-2.5-pro",
        help="Default Gemini model for Slack-triggered reviews",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "build":
        return run_build(args)
    if args.command == "run":
        return run_gemini(args)
    if args.command == "slack-serve":
        signing_secret = os.getenv(args.signing_secret_env, "").strip()
        if not signing_secret:
            print(f"{args.signing_secret_env} is not set", file=sys.stderr)
            return 1
        serve_slack_commands(
            host=args.host,
            port=args.port,
            signing_secret=signing_secret,
            default_model=args.default_model,
        )
        return 0
    return 1


def load_packet_from_args(args: argparse.Namespace):
    input_path = Path(args.input)
    schema_path = Path(args.schema)
    brief = load_brief(input_path)
    return build_packet_for_brief(brief, schema_path)


def run_build(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    skeleton_output = Path(args.skeleton_output)

    try:
        packet = load_packet_from_args(args)
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print(format_validation_issues(exc.issues), file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    skeleton_output.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(packet.markdown + "\n", encoding="utf-8")
    skeleton_output.write_text(
        json.dumps(packet.output_skeleton, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote prompt packet: {output_path}")
    print(f"Wrote output skeleton: {skeleton_output}")
    return 0


def run_gemini(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    packet_output = Path(args.packet_output)
    skeleton_output = Path(args.skeleton_output)
    raw_output = Path(args.raw_output)
    input_path = Path(args.input)
    schema_path = Path(args.schema)

    try:
        brief = load_brief(input_path)
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        print(format_validation_issues(exc.issues), file=sys.stderr)
        return 1

    try:
        run_review_for_brief(
            brief=brief,
            schema_path=schema_path,
            model=args.model,
            packet_output=packet_output,
            skeleton_output=skeleton_output,
            result_output=output_path,
            raw_output=raw_output,
        )
    except GeminiError as exc:
        print(format_gemini_error(str(exc)), file=sys.stderr)
        return 1

    print(f"Wrote prompt packet: {packet_output}")
    print(f"Wrote output skeleton: {skeleton_output}")
    print(f"Wrote raw Gemini response: {raw_output}")
    print(f"Wrote review result: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
