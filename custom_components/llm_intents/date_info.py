"""Date information tool."""

import logging
from datetime import date

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)


class DateInfoTool(BaseTool):
    """Tool for getting day-of-week and formatted date information."""

    name = "calendar_day_info"
    description = (
        "Get information about a specific date: what day of the week it falls on "
        "and its formatted representation. Useful for planning events or checking schedules."
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "day",
                description="The day of the month (1-31).",
            ): int,
            vol.Required(
                "month",
                description="The month (1-12, where 1 is January and 12 is December).",
            ): int,
            vol.Optional(
                "year",
                description="The year (optional, defaults to the current year).",
            ): int,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Return day-of-week and formatted date for the given date."""
        day = tool_input.tool_args["day"]
        month = tool_input.tool_args["month"]
        year = tool_input.tool_args.get("year") or date.today().year

        _LOGGER.debug("DateInfo: %s/%s/%s", month, day, year)

        try:
            d = date(year, month, day)
        except ValueError as e:
            return {"error": f"Invalid date {year}-{month:02d}-{day:02d}: {e}"}

        day_of_week = d.strftime("%A")
        formatted_date = d.strftime("%B %d, %Y")

        return {
            "day": day_of_week,
            "date": formatted_date,
            "message": f"{formatted_date} is a {day_of_week}",
        }
