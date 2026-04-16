import unittest
from unittest.mock import patch

from personalens.gemini import GeminiError
from personalens.service import generate_persona_from_form


class ServicePersonaFallbackTests(unittest.TestCase):
    @patch("personalens.service.fetch_webpage_context", return_value="- dummy website context")
    @patch("personalens.service.enrich_persona", side_effect=GeminiError("boom"))
    def test_generate_persona_falls_back_on_gemini_error(self, mock_enrich, mock_fetch):
        persona = generate_persona_from_form(
            {
                "service_name": "Example App",
                "service_url": "https://example.org",
                "service_type": "web app",
                "core_journey": "Sign up",
                "persona_description": "Busy founder",
                "business_goal": "Increase signups",
                "problems": "Unclear value",
                "competitors": "",
            },
            model="gemini-2.5-pro",
        )

        self.assertEqual(persona["name"], "Target User")
        self.assertIn("Example App", persona["job_to_be_done"])
        self.assertEqual(persona["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
