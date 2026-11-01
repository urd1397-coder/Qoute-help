import asyncio
import unittest

from app.browser_agent import PlaywrightQuoteAgent, ProviderUnavailable, _host_allowed, _money


class InvalidAdapter:
    provider_id = "invalid"
    display_name = "Invalid test provider"
    start_url = "http://example.test/quote"
    allowed_hosts = ("example.test",)


class BrowserAgentBoundaryTests(unittest.TestCase):
    def test_only_https_allowlisted_hosts_are_accepted(self):
        self.assertTrue(_host_allowed("https://quotes.example.test/path", ("example.test",)))
        self.assertFalse(_host_allowed("http://example.test/path", ("example.test",)))
        self.assertFalse(_host_allowed("https://example.test.attacker.test/", ("example.test",)))

    def test_money_parser(self):
        self.assertEqual(_money("$1,234.56"), 1234.56)
        self.assertEqual(_money("not itemized", required=False), 0.0)

    def test_unapproved_url_is_rejected_before_browser_launch(self):
        with self.assertRaises(ProviderUnavailable):
            asyncio.run(PlaywrightQuoteAgent().run(InvalidAdapter(), {}))


if __name__ == "__main__":
    unittest.main()
