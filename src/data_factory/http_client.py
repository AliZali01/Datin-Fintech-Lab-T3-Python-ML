
"""HTTP client with GET, POST, retry, and response validation."""

import time
from collections.abc import Mapping
from typing import Any, Callable

import requests

from .exceptions import DataValidationError, NetworkError


class HttpClient:
    """A reusable HTTP client for external data sources."""

    RETRYABLE_STATUS_CODES = frozenset({
        408, 429, 500, 502, 503, 504
    })

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_retries: int,
        backoff_factor_seconds: float,
        session: requests.Session | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor_seconds = backoff_factor_seconds
        self.session = session if session is not None else requests.Session()
        self.sleep_fn = sleep_fn

    
    @classmethod
    def from_config(
        cls,
        config: Mapping[str, Any],
        **kwargs,
    ) -> "HttpClient":
        """Create an HTTP client from project configuration."""

        api = config["api"]

        return cls(
            timeout_seconds=api["timeout_seconds"],
            max_retries=api["max_retries"],
            backoff_factor_seconds=api["backoff_factor_seconds"],
            **kwargs,
        )


    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        retry_post: bool = False,
    ) -> Any:
        """Send an HTTP request and return its decoded JSON response."""

        method = method.upper()

        if method not in {"GET", "POST"}:
            raise ValueError(f"Unsupported HTTP method: {method}")

        should_retry = method == "GET" or retry_post

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_body,
                    data=data,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )

            except requests.RequestException as exc:
                if should_retry and attempt < self.max_retries:
                    delay = self.backoff_factor_seconds * (2 ** attempt)
                    self.sleep_fn(delay)
                    continue

                raise NetworkError(
                    f"HTTP request failed: {exc}"
                ) from exc

            status = response.status_code

            if (
                status in self.RETRYABLE_STATUS_CODES
                and should_retry
                and attempt < self.max_retries
            ):
                delay = self.backoff_factor_seconds * (2 ** attempt)
                self.sleep_fn(delay)
                continue

            if not 200 <= status < 300:
                raise NetworkError(
                    f"HTTP {status} returned by {url}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise DataValidationError(
                    "API response is not valid JSON."
                ) from exc

        raise NetworkError("HTTP request exhausted all retry attempts.")

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Send a GET request."""

        return self.request(
            "GET",
            url,
            params=params,
            headers=headers,
        )

    def post(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        data: Any = None,
        headers: Mapping[str, str] | None = None,
        retry_post: bool = False,
    ) -> Any:
        """Send a POST request."""

        return self.request(
            "POST",
            url,
            params=params,
            json_body=json_body,
            data=data,
            headers=headers,
            retry_post=retry_post,
        )
