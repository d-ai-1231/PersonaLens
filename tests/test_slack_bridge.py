import hashlib
import hmac
import time
import unittest

from personalens.slack_bridge import build_form_from_slack_text, verify_slack_signature


class SlackBridgeTests(unittest.TestCase):
    def test_verify_slack_signature_accepts_valid_signature(self):
        secret = "topsecret"
        timestamp = str(int(time.time()))
        body = "command=%2Freview&text=https%3A%2F%2Fexample.com"
        base = f"v0:{timestamp}:{body}".encode("utf-8")
        digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()

        self.assertTrue(
            verify_slack_signature(
                signing_secret=secret,
                timestamp=timestamp,
                body=body,
                signature=f"v0={digest}",
                now=int(timestamp),
            )
        )

    def test_verify_slack_signature_rejects_stale_payload(self):
        secret = "topsecret"
        timestamp = "1000"
        body = "command=%2Freview"
        digest = hmac.new(secret.encode("utf-8"), f"v0:{timestamp}:{body}".encode("utf-8"), hashlib.sha256).hexdigest()

        self.assertFalse(
            verify_slack_signature(
                signing_secret=secret,
                timestamp=timestamp,
                body=body,
                signature=f"v0={digest}",
                now=2000,
            )
        )

    def test_build_form_from_slack_text_uses_reasonable_defaults(self):
        form = build_form_from_slack_text("https://example.com")

        self.assertEqual(form["service_url"], "https://example.com")
        self.assertEqual(form["service_name"], "Example")
        self.assertEqual(form["service_type"], "web product")
        self.assertIn("landing", form["core_journey"].lower())

    def test_build_form_from_slack_text_parses_pipe_separated_fields(self):
        form = build_form_from_slack_text(
            "https://example.com | My App | SaaS | Sign up | Busy founder | Grow activation | unclear value | Competitor A, Competitor B"
        )

        self.assertEqual(form["service_name"], "My App")
        self.assertEqual(form["service_type"], "SaaS")
        self.assertEqual(form["business_goal"], "Grow activation")
        self.assertEqual(form["competitors"], "Competitor A, Competitor B")


if __name__ == "__main__":
    unittest.main()
