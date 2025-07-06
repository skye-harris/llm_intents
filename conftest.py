# conftest.py
import pytest

@pytest.fixture(autouse=True)
def enable_custom_integrations():
    """Override HA-CC plugin’s enable_custom_integrations so it does nothing."""
    yield