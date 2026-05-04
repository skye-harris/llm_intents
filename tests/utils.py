"""
Common test utilities for LLM intents tests.

This module provides helper classes and functions used by tests but does not
contain test cases itself.
"""

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


def mock_session(status: int, data: dict) -> AsyncMock:
    """Create a mock HTTP session."""
    session = AsyncMock()

    def mock_get(*args: object, **kwargs: Any) -> MockContext:
        return MockContext(mock_response(status, data))

    session.get = Mock(side_effect=mock_get)
    return session


def mock_response(status: int, data: dict) -> AsyncMock:
    """Create a mock HTTP response."""
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=data)
    return response
