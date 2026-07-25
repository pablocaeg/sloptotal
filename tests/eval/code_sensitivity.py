"""Sensitivity half of the code-detection test.

The specificity half used CPython stdlib and produced 0/6 false positives. That
says the engines do not slander human code; it says nothing about whether they
can *catch* AI code.

These samples are genuine LLM output: written by Claude (Opus 5) in the style it
naturally produces for ordinary "write me a function" requests -- exhaustive
docstrings, type hints everywhere, defensive validation, tidy helper decomposition.
That is real ground truth for the positive class.
"""
import json
import urllib.request

API = "https://api.sloptotal.com/api/analyze"

SAMPLES = {
"cache-decorator": '''
from typing import Any, Callable, Dict, Optional, TypeVar
from functools import wraps
import time

T = TypeVar("T")


class TTLCache:
    """A simple time-to-live cache with a maximum size.

    This cache stores key-value pairs and automatically expires entries after a
    configurable time-to-live period. When the cache reaches its maximum size,
    the oldest entry is evicted to make room for new entries.

    Attributes:
        max_size: The maximum number of entries the cache can hold.
        ttl: The time-to-live for each entry, in seconds.
    """

    def __init__(self, max_size: int = 128, ttl: float = 300.0) -> None:
        """Initialize the cache.

        Args:
            max_size: Maximum number of entries. Must be positive.
            ttl: Time-to-live in seconds. Must be positive.

        Raises:
            ValueError: If max_size or ttl is not positive.
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        self.max_size = max_size
        self.ttl = ttl
        self._store: Dict[Any, tuple[Any, float]] = {}

    def get(self, key: Any) -> Optional[Any]:
        """Retrieve a value from the cache.

        Args:
            key: The key to look up.

        Returns:
            The cached value, or None if the key is absent or expired.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        value, timestamp = entry
        if time.monotonic() - timestamp > self.ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        """Store a value in the cache.

        Args:
            key: The key to store under.
            value: The value to store.
        """
        if len(self._store) >= self.max_size and key not in self._store:
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
        self._store[key] = (value, time.monotonic())
''',

"binary-search": '''
from typing import List, Optional


def binary_search(items: List[int], target: int) -> Optional[int]:
    """Perform a binary search on a sorted list.

    This function implements the classic binary search algorithm, which
    repeatedly divides the search interval in half. It has a time complexity of
    O(log n) and a space complexity of O(1).

    Args:
        items: A list of integers sorted in ascending order.
        target: The value to search for.

    Returns:
        The index of the target if found, otherwise None.

    Example:
        >>> binary_search([1, 3, 5, 7, 9], 5)
        2
        >>> binary_search([1, 3, 5, 7, 9], 4)
        None
    """
    if not items:
        return None

    left = 0
    right = len(items) - 1

    while left <= right:
        middle = (left + right) // 2
        candidate = items[middle]

        if candidate == target:
            return middle
        elif candidate < target:
            left = middle + 1
        else:
            right = middle - 1

    return None


def validate_sorted(items: List[int]) -> bool:
    """Check whether a list is sorted in ascending order.

    Args:
        items: The list to validate.

    Returns:
        True if the list is sorted, False otherwise.
    """
    return all(items[i] <= items[i + 1] for i in range(len(items) - 1))
''',

"api-client": '''
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class APIResponse:
    """Represents a response from the API.

    Attributes:
        status_code: The HTTP status code returned by the server.
        data: The parsed JSON payload, if any.
        error: An error message, if the request failed.
    """

    status_code: int
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        """Return True if the response indicates success."""
        return 200 <= self.status_code < 300


class APIClient:
    """A robust client for interacting with a REST API.

    This client handles authentication, retries, and error handling in a
    consistent manner, making it straightforward to interact with the API.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        """Initialize the API client.

        Args:
            base_url: The base URL of the API.
            api_key: The API key used for authentication.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> APIResponse:
        """Send a GET request to the specified endpoint.

        Args:
            endpoint: The API endpoint, relative to the base URL.
            params: Optional query parameters.

        Returns:
            An APIResponse containing the result of the request.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            return APIResponse(status_code=response.status_code, data=response.json())
        except requests.exceptions.RequestException as exc:
            logger.error("Request to %s failed: %s", url, exc)
            return APIResponse(status_code=0, error=str(exc))
''',
}


def analyze(text):
    req = urllib.request.Request(
        API,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json", "Origin": "https://sloptotal.com"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


print(f"{'LLM-written sample':22} {'score':>6}  verdict")
print("-" * 62)
rows = []
for name, src in SAMPLES.items():
    d = analyze(src.strip())
    rows.append((name, d["overall_score"], d["overall_verdict"]))
    print(f"{name:22} {d['overall_score']:6.1f}  {d['overall_verdict']}")

caught = [r for r in rows if r[1] >= 60]
print(f"\n{len(rows)} genuine LLM code samples: {len(caught)} caught at >=60 'Likely AI'")
json.dump(rows, open("code_sensitivity_results.json", "w"), indent=1)
