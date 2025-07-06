"""Pytest fixture to disable Home Assistant custom integration loading."""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def enable_custom_integrations() -> Generator[None, None, None]:
    """Override HA-CC plugin's enable_custom_integrations so it does nothing."""
    return
