"""Tests for the DateInfoTool."""

import json

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.llm_intents.date_info import DateInfoTool


@pytest.fixture
def date_info_tool(hass: HomeAssistant) -> DateInfoTool:
    """Create DateInfoTool instance."""
    config = {"date_info_enabled": True}
    return DateInfoTool(config, hass)


@pytest.mark.parametrize(
    ("tool_input_json", "expected_day", "expected_date", "expected_message"),
    [
        # Fixed year — well-known dates
        (
            '{"day": 1, "month": 1, "year": 2024}',
            "Monday",
            "January 01, 2024",
            "January 01, 2024 is a Monday",
        ),
        (
            '{"day": 4, "month": 7, "year": 2024}',
            "Thursday",
            "July 04, 2024",
            "July 04, 2024 is a Thursday",
        ),
        (
            '{"day": 25, "month": 12, "year": 2024}',
            "Wednesday",
            "December 25, 2024",
            "December 25, 2024 is a Wednesday",
        ),
        # Leap year
        (
            '{"day": 29, "month": 2, "year": 2024}',
            "Thursday",
            "February 29, 2024",
            "February 29, 2024 is a Thursday",
        ),
        # No year provided — defaults to current year (frozen)
        (
            '{"day": 15, "month": 6}',
            "Monday",
            "June 15, 2026",
            "June 15, 2026 is a Monday",
        ),
        (
            '{"month": 3, "day": 1}',
            "Sunday",
            "March 01, 2026",
            "March 01, 2026 is a Sunday",
        ),
    ],
)
@pytest.mark.freeze_time("2026-01-15")
async def test_date_info_valid(
    hass: HomeAssistant,
    date_info_tool: DateInfoTool,
    tool_input_json: str,
    expected_day: str,
    expected_date: str,
    expected_message: str,
) -> None:
    """Test valid date inputs with parametrize."""
    tool_input = llm.ToolInput(
        tool_name="calendar_day_info", tool_args=json.loads(tool_input_json)
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await date_info_tool.async_call(hass, tool_input, llm_context)

    assert result["day"] == expected_day
    assert result["date"] == expected_date
    assert result["message"] == expected_message


@pytest.mark.parametrize(
    "tool_input_json",
    [
        # Invalid month
        '{"day": 1, "month": 13, "year": 2024}',
        # Invalid day for month
        '{"day": 31, "month": 2, "year": 2024}',
        # Day out of range
        '{"day": 0, "month": 1, "year": 2024}',
        # Negative day
        '{"day": -1, "month": 1, "year": 2024}',
    ],
)
async def test_date_info_invalid(
    hass: HomeAssistant,
    date_info_tool: DateInfoTool,
    tool_input_json: str,
) -> None:
    """Test invalid dates return an error dict."""
    tool_input = llm.ToolInput(
        tool_name="calendar_day_info", tool_args=json.loads(tool_input_json)
    )
    llm_context = llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )

    result = await date_info_tool.async_call(hass, tool_input, llm_context)

    assert "error" in result
