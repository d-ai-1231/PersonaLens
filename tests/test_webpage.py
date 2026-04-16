import unittest

from personalens.webpage import fetch_webpage_context, prepare_request_url


class PrepareRequestUrlSafetyTests(unittest.TestCase):
    def test_blocks_loopback_and_private_targets(self):
        blocked = [
            "http://127.0.0.1",
            "http://localhost",
            "http://10.0.0.5",
            "http://172.16.0.10",
            "http://192.168.1.20",
            "http://169.254.0.1",
        ]

        for url in blocked:
            with self.subTest(url=url):
                self.assertEqual(prepare_request_url(url), "")

    def test_keeps_public_http_targets(self):
        self.assertEqual(
            prepare_request_url("https://93.184.216.34/path?q=1#frag"),
            "https://93.184.216.34/path?q=1",
        )

    def test_fetch_webpage_context_explains_blocked_local_targets(self):
        message = fetch_webpage_context("http://localhost")
        self.assertIn("blocked", message.lower())


if __name__ == "__main__":
    unittest.main()
