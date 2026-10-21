"""Pytest configuration for the llm_intents test suite."""

import logging

import pytest


@pytest.fixture(autouse=True)
def suppress_sqlalchemy_logs() -> None:
    """Suppress SQLAlchemy INFO-level log spam from recorder_mock."""
    logger = logging.getLogger("sqlalchemy.engine.Engine")
    logger.setLevel(logging.WARNING)
