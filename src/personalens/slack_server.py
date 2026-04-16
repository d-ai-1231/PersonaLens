from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import strftime, gmtime
from urllib.parse import parse_qs, urlparse
import urllib.error
import urllib.request

from .diagnostics import format_gemini_error, format_unexpected_error, format_validation_issues
from .gemini import GeminiError
from .models import ValidationError
from .service import create_brief_from_form, run_review_for_brief
from .slack_bridge import SlackReviewRequest, parse_review_request, verify_slack_signature

MAX_SLACK_MESSAGE_CHARS = 3500


@dataclass(frozen=True)
class SlackCommandConfig:
    signing_secret: str
    default_model: str = "gemini-2.5-pro"
    host: str = "127.0.0.1"
    port: int = 8787
    route_path: str = "/slack/commands"


class SlackCommandHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, config: SlackCommandConfig):
        super().__init__(server_address, RequestHandlerClass)
        self.config = config


class SlackCommandHandler(BaseHTTPRequestHandler):
    server: SlackCommandHTTPServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != self.server.config.route_path:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        body_bytes = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        body = body_bytes.decode("utf-8")
        timestamp = self.headers.get("X-Slack-Request-Timestamp", "")
        signature = self.headers.get("X-Slack-Signature", "")
        if not verify_slack_signature(self.server.config.signing_secret, timestamp, body, signature):
            self._send_json({"error": "invalid signature"}, status=HTTPStatus.UNAUTHORIZED)
            return

        form = {key: values[0] for key, values in parse_qs(body).items()}
        command = form.get("command", "").strip()
        if command != "/review":
            self._send_json(
                {
                    "response_type": "ephemeral",
                    "text": "Supported command: /review <url> | <service name> | <service type> | <journey> | <persona> | <goal> | <problems> | <competitors>",
                }
            )
            return

        text = form.get("text", "").strip()
        response_url = form.get("response_url", "").strip()
        if not response_url:
            self._send_json({"error": "missing response_url"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            request = parse_review_request(text, model=self.server.config.default_model)
        except ValueError as exc:
            self._send_json({"response_type": "ephemeral", "text": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        threading.Thread(target=self.server.process_review_request, args=(request, response_url), daemon=True).start()
        self._send_json(
            {
                "response_type": "ephemeral",
                "text": f"Got it — running a review for {request.service_name}. I'll reply here when it's done.",
            }
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def serve_slack_commands(host: str, port: int, signing_secret: str, default_model: str = "gemini-2.5-pro") -> None:
    config = SlackCommandConfig(signing_secret=signing_secret, default_model=default_model, host=host, port=port)
    server = SlackCommandHTTPServer((host, port), SlackCommandHandler, config)
    server.process_review_request = _process_review_request.__get__(server, SlackCommandHTTPServer)  # type: ignore[attr-defined]
    print(f"Slack bridge running at http://{host}:{port}{config.route_path}")
    server.serve_forever()


def _process_review_request(server: SlackCommandHTTPServer, request: SlackReviewRequest, response_url: str) -> None:
    build_dir = Path("build/slack")
    build_dir.mkdir(parents=True, exist_ok=True)
    form = request.to_form()
    timestamp = strftime("%Y%m%d-%H%M%S", gmtime())
    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in request.service_name.lower()) or "review"
    packet_output = build_dir / f"{safe_name}-{timestamp}-packet.md"
    skeleton_output = build_dir / f"{safe_name}-{timestamp}-skeleton.json"
    result_output = build_dir / f"{safe_name}-{timestamp}-result.json"
    raw_output = build_dir / f"{safe_name}-{timestamp}-raw.json"

    try:
        brief = create_brief_from_form(form, model=request.model)
        result = run_review_for_brief(
            brief=brief,
            schema_path=Path("review-output-schema.json"),
            model=request.model,
            packet_output=packet_output,
            skeleton_output=skeleton_output,
            result_output=result_output,
            raw_output=raw_output,
        )
        message = format_review_result_for_slack(result, service_name=request.service_name)
    except ValidationError as exc:
        message = format_validation_issues(exc.issues)
    except GeminiError as exc:
        message = format_gemini_error(str(exc))
    except Exception as exc:
        message = format_unexpected_error(str(exc), "running the Slack review")

    post_slack_response(response_url, message)


def format_review_result_for_slack(result: dict, service_name: str = "Target service") -> str:
    summary = result.get("review_summary") or {}
    findings = result.get("findings") or []
    improvements = result.get("prioritized_improvements") or {}
    quick_wins = improvements.get("quick_wins") or []
    structural_fixes = improvements.get("structural_fixes") or []

    lines = [
        f"*{service_name} review*",
        f"Verdict: {summary.get('verdict', 'N/A')}",
    ]
    if summary.get("first_impression"):
        lines.append(f"First impression: {summary['first_impression']}")

    if findings:
        lines.append("Top findings:")
        for item in findings[:3]:
            priority = item.get("priority", "?")
            title = item.get("title", "Untitled finding")
            lines.append(f"• [{priority}] {title}")

    if quick_wins:
        lines.append("Quick wins:")
        for item in quick_wins[:2]:
            lines.append(f"• {item.get('change', '—')}")

    if structural_fixes:
        lines.append("Structural fixes:")
        for item in structural_fixes[:2]:
            lines.append(f"• {item.get('change', '—')}")

    message = "\n".join(lines).strip()
    if len(message) > MAX_SLACK_MESSAGE_CHARS:
        message = message[: MAX_SLACK_MESSAGE_CHARS - 3] + "..."
    return message


def post_slack_response(response_url: str, text: str) -> None:
    if not response_url:
        return
    payload = json.dumps({"response_type": "in_channel", "text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        response_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20):
            return
    except urllib.error.URLError:
        return
