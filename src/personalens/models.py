from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


class ValidationError(Exception):
    def __init__(self, issues: list[str]):
        super().__init__("Invalid review brief")
        self.issues = issues


@dataclass
class Service:
    name: str
    url: str
    type: str


@dataclass
class Persona:
    name: str
    segment: str
    job_to_be_done: str
    context: str
    goals: list[str]
    pain_points: list[str]
    technical_level: str
    decision_style: str
    device_context: str
    access_needs: list[str]
    success_definition: str
    voice: list[str]
    evidence_sources: list[str]
    confidence: str


@dataclass
class ReviewBrief:
    service: Service
    review_goal: str
    core_journey: str
    business_goal: str
    persona: Persona
    evidence: list[str]
    known_constraints: list[str]
    notes: list[str]
    competitors: list[str] = None

    def __post_init__(self):
        if self.competitors is None:
            self.competitors = []

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewBrief":
        service = Service(**data["service"])
        persona = Persona(**data["persona"])
        return cls(
            service=service,
            review_goal=data["review_goal"],
            core_journey=data["core_journey"],
            business_goal=data["business_goal"],
            persona=persona,
            evidence=data.get("evidence", []),
            known_constraints=data.get("known_constraints", []),
            notes=data.get("notes", []),
            competitors=data.get("competitors", []),
        )

    def validate(self) -> list[str]:
        issues: list[str] = []

        if not self.review_goal.strip():
            issues.append("review_goal is required")
        if not self.core_journey.strip():
            issues.append("core_journey is required")
        if not self.business_goal.strip():
            issues.append("business_goal is required")

        if not self.service.name.strip():
            issues.append("service.name is required")
        if not self.service.url.strip():
            issues.append("service.url is required")
        else:
            parsed = urlparse(self.service.url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                issues.append("service.url must be a valid http/https URL")
            if parsed.netloc == "example.com":
                issues.append("service.url must point to the actual service, not example.com")
        if not self.service.type.strip():
            issues.append("service.type is required")

        persona = self.persona
        if not persona.name.strip():
            issues.append("persona.name is required")
        if not persona.segment.strip():
            issues.append("persona.segment is required")
        if not persona.job_to_be_done.strip():
            issues.append("persona.job_to_be_done is required")
        if not persona.context.strip():
            issues.append("persona.context is required")
        if len(persona.goals) < 1:
            issues.append("persona.goals must contain at least 1 item")
        if len(persona.pain_points) < 1:
            issues.append("persona.pain_points must contain at least 1 item")
        if len(persona.voice) < 3:
            issues.append("persona.voice should contain at least 3 anchors")
        if len(persona.evidence_sources) < 1:
            issues.append("persona.evidence_sources must contain at least 1 item")
        if persona.confidence not in {"low", "medium", "high"}:
            issues.append("persona.confidence must be one of: low, medium, high")
        if persona.device_context not in {"mobile", "desktop", "mixed"}:
            issues.append("persona.device_context must be one of: mobile, desktop, mixed")

        return issues
