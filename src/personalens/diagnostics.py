from __future__ import annotations


def format_validation_issues(issues: list[str]) -> str:
    if not issues:
        return "Input validation failed."
    bullet_list = "\n".join(f"- {issue}" for issue in issues)
    return f"Input validation failed:\n{bullet_list}"


def format_gemini_error(message: str) -> str:
    normalized = message.strip()
    lowered = normalized.lower()

    if "not set" in lowered and "api_key" in lowered:
        return (
            f"Gemini request failed: {normalized}. "
            "API key missing: set the GEMINI_API_KEY environment variable and try again."
        )

    if lowered.startswith("http "):
        return (
            f"Gemini request failed: {normalized}. "
            "Check your API quota, request payload, and model name."
        )

    if "network error" in lowered:
        return (
            f"Gemini request failed: {normalized}. "
            "Check your internet connection and proxy settings."
        )

    return f"Gemini request failed: {normalized}"


def format_unexpected_error(message: str, context: str = "") -> str:
    prefix = f"Unexpected error while {context}:" if context else "Unexpected error:"
    return f"{prefix} {message}"
