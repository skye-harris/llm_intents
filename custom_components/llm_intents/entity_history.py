"""Entity history tool."""

import logging
import re
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.components import recorder
from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool
from .utils import find_entity_by_name

_LOGGER = logging.getLogger(__name__)


def _to_datetime(dt: str) -> datetime:
    try:
        res = re.search(r"(\d{4}-\d{2}-\d{2})\W?(\d{1,2}:\d{2})?", dt)
        result = res[0].strip()
        format_str = "%Y-%m-%d" if len(result) == 8 else "%Y-%m-%d %H:%M"
        return datetime.strptime(result, format_str).astimezone()
    except Exception as ex:
        raise HomeAssistantError(f"Failed to parse date {dt}: {ex}")


class EntityHistoryTool(BaseTool):
    """Tool for getting the significant change history of a device or entity."""

    name = "get_device_history_context"
    description = (
        "Where the `GetLiveContext` tool provides live device states, the `get_entity_context_history` tool is used to retrieve the past (historic, previous) states of a device.\n"
        "This tool must be used any time the user requests information on when a device changed state, or what a devices state was at an earlier day or time.\n"
        "You must make use of the `start_date_time` and `end_date_time` arguments to specify the search period, but ensure this is not too small that it does not cover the time period intended by the user.\n"
        "- If the user does not specify, search FROM yesterdays date UNTIL today's date.\n"
        "- If the user wants to know the device state at an exact time, limit the start and end date/time arguments to exactly that date and time.\n"
        "- If the user wants information for a particular time period, such as the morning, evening, or overnight, ensure that the start and end times encapsulate the entire duration.\n"
        "- If the user wants to know the last time something changed, ensure to use the current date and time as the search end time.\n"
        "Example queries: `What time did the kitchen reach 25 degrees?` `When was the bedroom light turned off?` `What was the temperature outside at 8am this morning?`"
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "entity_name",
                description="The name of the entity or device to retrieve the history for, exactly as it appears in the static device context.",
            ): str,
            vol.Required(
                "end_date_time",
                description="The end date/time of the period to retrieve information from, in the format: `YYYY-MM-DD HH:MM`.",
            ): str,
            vol.Required(
                "start_date_time",
                description="The start date/time of the period to retrieve information from, in the format: ``YYYY-MM-DD HH:MM`.",
            ): str,
        }
    )

    @staticmethod
    def format_result(state: State | dict[str, Any]) -> dict[str, Any]:
        result = state.as_dict() if isinstance(state, State) else state

        for key in ["last_changed", "last_updated"]:
            if key in result:
                dt = datetime.fromisoformat(result[key]).astimezone()
                result[key] = dt.strftime("%a %e %b %Y, %I:%M %p")

        return result

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Return state change history of the device entity."""
        entity_name = tool_input.tool_args.get("entity_name").lower().strip()
        start_time = tool_input.tool_args.get("start_date_time")
        end_time = tool_input.tool_args.get("end_date_time")

        try:
            # Assist puts the entity name into static context, so we must look-up by name
            entity = find_entity_by_name(hass, entity_name)
            entity_id = entity.entity_id
        except RuntimeError:
            raise HomeAssistantError("Could not find entity")

        start_time = _to_datetime(start_time)
        end_time = _to_datetime(end_time)

        with recorder.util.session_scope(hass=hass, read_only=True) as session:
            result = await recorder.get_instance(hass).async_add_executor_job(
                history.get_significant_states_with_session,
                hass,
                session,
                start_time,
                end_time,
                [entity_id],
                None,  # filters
                True,  # include_start_time_state,
                True,  # significant_changes_only,
                True,  # minimal_response,
                True,  # no_attributes,
            )

        results = {}
        for sublist in result.values():
            sublist_results = [self.format_result(item) for item in sublist]

            initial_state = sublist_results.pop(0)
            results["state_at_search_start"] = initial_state.get('state')

            # Filter unavailable/unknown values
            sublist_results = [item for item in sublist_results if item.get('state') not in ["unavailable", "unknown"]]

            if sublist_results:
                results["search_duration_state_changes"] = sublist_results

            results["instruction"] = "Answer the users question in a naturally-spoken manner"

        return results
