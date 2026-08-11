from unittest.mock import patch

from django.test import SimpleTestCase

from config.monitoring import initialize_sentry


class SentryMonitoringTest(SimpleTestCase):
    @patch("config.monitoring.sentry_sdk.init")
    def test_dsn_unset_disables_monitoring(self, init_mock):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(initialize_sentry())
        init_mock.assert_not_called()

    @patch("config.monitoring.sentry_sdk.init")
    def test_dsn_enables_privacy_safe_monitoring(self, init_mock):
        env = {
            "SENTRY_DSN": "https://public@example.invalid/1",
            "SENTRY_ENVIRONMENT": "test",
            "SENTRY_RELEASE": "test-release",
        }
        with patch.dict("os.environ", env, clear=True):
            self.assertTrue(initialize_sentry())

        kwargs = init_mock.call_args.kwargs
        self.assertEqual(kwargs["environment"], "test")
        self.assertEqual(kwargs["release"], "test-release")
        self.assertFalse(kwargs["send_default_pii"])
        self.assertEqual(kwargs["max_request_body_size"], "never")
        self.assertEqual(kwargs["traces_sample_rate"], 0.0)

    def test_event_scrubber_removes_request_secrets(self):
        from config.monitoring import _scrub_event

        event = {
            "request": {
                "data": {"password": "secret"},
                "cookies": {"sessionid": "secret"},
                "headers": {
                    "Authorization": "Bearer secret",
                    "Cookie": "sessionid=secret",
                    "X-CSRFToken": "secret",
                    "Accept": "application/json",
                },
            },
        }
        scrubbed = _scrub_event(event, {})
        request = scrubbed["request"]
        self.assertNotIn("data", request)
        self.assertNotIn("cookies", request)
        self.assertEqual(request["headers"], {"Accept": "application/json"})
