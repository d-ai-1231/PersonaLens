import unittest

from personalens.diagnostics import format_gemini_error, format_validation_issues


class DiagnosticsFormattingTests(unittest.TestCase):
    def test_validation_issues_are_rendered_as_bullets(self):
        message = format_validation_issues(["service.url is required", "persona.name is required"])
        self.assertIn("Input validation failed:", message)
        self.assertIn("- service.url is required", message)
        self.assertIn("- persona.name is required", message)

    def test_gemini_missing_key_message_is_actionable(self):
        message = format_gemini_error("GEMINI_API_KEY is not set")
        self.assertIn("API key", message)
        self.assertIn("GEMINI_API_KEY", message)

    def test_gemini_http_error_keeps_status_and_hints_next_step(self):
        message = format_gemini_error("HTTP 429: rate limited")
        self.assertIn("429", message)
        self.assertIn("Gemini request failed", message)


if __name__ == "__main__":
    unittest.main()
