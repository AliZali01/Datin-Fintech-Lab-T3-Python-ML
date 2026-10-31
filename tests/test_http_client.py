
"""Offline tests for the HTTP client."""

import unittest
from unittest.mock import Mock

import requests

from data_factory.http_client import HttpClient
from data_factory.exceptions import NetworkError, DataValidationError


def make_response(status=200, payload=None, json_error=None):
    response = Mock()
    response.status_code = status

    if json_error:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload

    return response


class TestHttpClient(unittest.TestCase):
    
    def test_client_can_be_created_from_config(self):
        config = {
            "api": {
                "timeout_seconds": 30,
                "max_retries": 3,
                "backoff_factor_seconds": 0.5,
            }
        }

        client = HttpClient.from_config(
            config,
            session=self.session,
            sleep_fn=self.sleep,
        )

        self.assertEqual(client.timeout_seconds, 30)
        self.assertEqual(client.max_retries, 3)
        self.assertEqual(client.backoff_factor_seconds, 0.5)

    def setUp(self):
        self.session = Mock()
        self.sleep = Mock()

        self.client = HttpClient(
            timeout_seconds=10,
            max_retries=2,
            backoff_factor_seconds=0.5,
            session=self.session,
            sleep_fn=self.sleep,
        )

    def test_get_request(self):
        self.session.request.return_value = make_response(
            payload=[{"id": 1}]
        )

        result = self.client.get(
            "https://example.com/data",
            params={"limit": 10},
        )

        self.assertEqual(result, [{"id": 1}])
        self.assertEqual(
            self.session.request.call_args.kwargs["method"],
            "GET",
        )

    def test_post_request(self):
        self.session.request.return_value = make_response(
            payload={"success": True}
        )

        result = self.client.post(
            "https://example.com/query",
            json_body={"query": "SELECT *"},
        )

        self.assertEqual(result, {"success": True})
        self.assertEqual(
            self.session.request.call_args.kwargs["method"],
            "POST",
        )
        self.assertEqual(
            self.session.request.call_args.kwargs["json"],
            {"query": "SELECT *"},
        )

    def test_retries_temporary_server_error(self):
        self.session.request.side_effect = [
            make_response(status=503),
            make_response(payload={"success": True}),
        ]

        result = self.client.get("https://example.com/data")

        self.assertEqual(result, {"success": True})
        self.assertEqual(self.session.request.call_count, 2)
        self.sleep.assert_called_once_with(0.5)

    def test_does_not_retry_client_error(self):
        self.session.request.return_value = make_response(status=400)

        with self.assertRaises(NetworkError):
            self.client.get("https://example.com/data")

        self.assertEqual(self.session.request.call_count, 1)

    def test_invalid_json_raises_validation_error(self):
        self.session.request.return_value = make_response(
            json_error=ValueError("Invalid JSON")
        )

        with self.assertRaises(DataValidationError):
            self.client.get("https://example.com/data")

    def test_network_failure_uses_retry_policy(self):
        self.session.request.side_effect = requests.Timeout(
            "Connection timed out"
        )

        with self.assertRaises(NetworkError):
            self.client.get("https://example.com/data")

        self.assertEqual(self.session.request.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_post_is_not_retried_by_default(self):
        self.session.request.return_value = make_response(status=503)

        with self.assertRaises(NetworkError):
            self.client.post("https://example.com/query")

        self.assertEqual(self.session.request.call_count, 1)

    def test_post_can_retry_when_explicitly_enabled(self):
        self.session.request.side_effect = [
            make_response(status=503),
            make_response(payload={"success": True}),
        ]

        result = self.client.post(
            "https://example.com/query",
            json_body={"query": "SELECT *"},
            retry_post=True,
        )

        self.assertEqual(result, {"success": True})
        self.assertEqual(self.session.request.call_count, 2)

    def test_unsupported_method_is_rejected(self):
        with self.assertRaises(ValueError):
            self.client.request("PUT", "https://example.com/data")


if __name__ == "__main__":
    unittest.main()
