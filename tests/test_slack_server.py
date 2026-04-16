import unittest

from personalens.slack_server import format_review_result_for_slack


class SlackServerFormattingTests(unittest.TestCase):
    def test_format_review_result_includes_verdict_and_top_finding(self):
        message = format_review_result_for_slack(
            {
                "review_summary": {"verdict": "Needs work", "first_impression": "Too vague"},
                "findings": [
                    {"priority": "High", "title": "Weak CTA"},
                    {"priority": "Medium", "title": "Unclear value"},
                ],
                "prioritized_improvements": {"quick_wins": [{"change": "Add CTA"}]},
            },
            service_name="Example",
        )

        self.assertIn("Needs work", message)
        self.assertIn("Weak CTA", message)
        self.assertIn("Quick wins", message)


if __name__ == "__main__":
    unittest.main()
