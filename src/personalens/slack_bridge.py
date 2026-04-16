from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

SLACK_SIGNATURE_VERSION = "v0"
SLACK_TIMESTAMP_TOLERANCE_SECONDS = 60 * 5
DEFAULT_SERVICE_TYPE = "web product"
DEFAULT_CORE_JOURNEY = "Review the landing page and onboarding flow"
DEFAULT_PERSONA_DESCRIPTION = "A user deciding whether this product is worth using"
DEFAULT_BUSINESS_GOAL = "Improve the primary landing-to-onboarding conversion"


@dataclass(frozen=True)
class SlackReviewRequest:
    service_url: str
    service_name: str
    service_type: str = DEFAULT_SERVICE_TYPE
    core_journey: str = DEFAULT_CORE_JOURNEY
    persona_description: str = DEFAULT_PERSONA_DESCRIPTION
    business_goal: str = DEFAULT_BUSINESS_GOAL
    problems: str = ""
    competitors: str = ""
    model: str = "gemini-2.5-pro"

    def to_form(self) -> dict[str, str]:
        return {
            "service_name": self.service_name,
            "service_url": self.service_url,
            "service_type": self.service_type,
            "core_journey": self.core_journey,
            "persona_description": self.persona_description,
            "business_goal": self.business_goal,
            "problems": self.problems,
            "competitors": self.competitors,
            "model": self.model,
        }


def build_form_from_slack_text(text: str, model: str = "gemini-2.5-pro") -> dict[str, str]:
    request = parse_review_request(text, model=model)
    return request.to_form()


def parse_review_request(text: str, model: str = "gemini-2.5-pro") -> SlackReviewRequest:
    parts = [part.strip() for part in re.split(r"\s*\|\s*|\n+", text.strip()) if part.strip()]
    if not parts:
        raise ValueError("Slack review text is required")

    service_url = parts[0]
    if not _looks_like_http_url(service_url):
        raise ValueError("First field must be a valid http/https URL")

    service_name = parts[1] if len(parts) > 1 and parts[1] else default_service_name(service_url)
    service_type = parts[2] if len(parts) > 2 and parts[2] else DEFAULT_SERVICE_TYPE
    core_journey = parts[3] if len(parts) > 3 and parts[3] else DEFAULT_CORE_JOURNEY
    persona_description = parts[4] if len(parts) > 4 and parts[4] else DEFAULT_PERSONA_DESCRIPTION
    business_goal = parts[5] if len(parts) > 5 and parts[5] else DEFAULT_BUSINESS_GOAL
    problems = parts[6] if len(parts) > 6 else ""
    competitors = parts[7] if len(parts) > 7 else ""

    return SlackReviewRequest(
        service_url=service_url,
        service_name=service_name,
        service_type=service_type,
        core_journey=core_journey,
        persona_description=persona_description,
        business_goal=business_goal,
        problems=problems,
        competitors=competitors,
        model=model,
    )


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: str,
    signature: str,
    now: int | None = None,
    max_age_seconds: int = SLACK_TIMESTAMP_TOLERANCE_SECONDS,
) -> bool:
    if not signing_secret or not timestamp or not body or not signature:
        return False

    try:
        ts = int(timestamp)
    except ValueError:
        return False

    current_time = int(now if now is not None else time.time())
    if abs(current_time - ts) > max_age_seconds:
        return False

    if not signature.startswith(f"{SLACK_SIGNATURE_VERSION}="):
        return False

    base_string = f"{SLACK_SIGNATURE_VERSION}:{timestamp}:{body}".encode("utf-8")
    expected = hmac.new(signing_secret.encode("utf-8"), base_string, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"{SLACK_SIGNATURE_VERSION}={expected}")


def default_service_name(service_url: str) -> str:
    parsed = urlparse(service_url)
    host = parsed.hostname or parsed.netloc or ""
    if not host:
        return "Target User"
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    label = host.split(".")[0] if "." in host else host
    label = re.sub(r"[^a-zA-Z0-9]+", " ", label).strip()
    return label.title() if label else "Target User"


def _looks_like_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
