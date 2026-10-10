"""
Common test utilities for LLM intents tests.

This module provides helper classes and functions used by tests but does not
contain test cases itself.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, Mock


class MockContext:
    """
    Mock async context manager for HTTP responses.

    Used to simulate aiohttp's async with statement pattern for HTTP requests.
    """

    def __init__(self, response: AsyncMock) -> None:
        """Initialize with a response object."""
        self.response = response

    async def __aenter__(self) -> AsyncMock:
        """Return the response when entering the context."""
        return self.response

    async def __aexit__(self, *args: object) -> None:
        """Clean up when exiting the context."""


def mock_session(status: int, data: dict, text: str | None = None) -> AsyncMock:
    """Create a mock HTTP session."""
    session = AsyncMock()

    def mock_request(*args: object, **kwargs: Any) -> MockContext:
        return MockContext(mock_response(status, data, text))

    session.get = Mock(side_effect=mock_request)
    session.post = Mock(side_effect=mock_request)
    return session


def mock_response(status: int, data: dict, text: str | None = None) -> AsyncMock:
    """
    Create a mock HTTP response.

    `text` is what the body looks like as raw text, which is what an error path
    reads. It defaults to the JSON form of `data`.
    """
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=data)
    response.text = AsyncMock(
        return_value=text if text is not None else json.dumps(data or {})
    )
    return response
