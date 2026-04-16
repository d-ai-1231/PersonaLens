import json
import unittest
from unittest.mock import MagicMock, patch

from personalens.gemini import GeminiConfig, _make_request


class GeminiTimeoutTests(unittest.TestCase):
    @patch("personalens.gemini.urllib.request.urlopen")
    def test_make_request_uses_timeout(self, mock_urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"ok": True}).encode("utf-8")
        mock_urlopen.return_value = response

        config = GeminiConfig(model="gemini-2.5-pro")
        _make_request(config, "test-key", {"contents": []})

        _, kwargs = mock_urlopen.call_args
        self.assertIn("timeout", kwargs)
        self.assertGreater(kwargs["timeout"], 0)


if __name__ == "__main__":
    unittest.main()
