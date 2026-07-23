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


class InvalidDateTimeError(HomeAssistantError):
    """Exception raised for invalid date/time strings."""

    def __init__(self, dt: str, original_error: Exception) -> None:
        """Initialize the exception."""
        super().__init__(f"Failed to parse date {dt}: {original_error}")


# Maximum individual state records returned to the LLM.
# High-frequency sensors (e.g. temperature) can produce thousands of data
# points in a short window — this caps context usage while preserving
# the overall shape via summary stats + even downsampling.
MAX_HISTORY_RESULTS = 30


def _to_datetime(dt: str) -> datetime:
    try:
        res = re.search(r"(\d{4}-\d{2}-\d{2})\W?(\d{1,2}:\d{2})?", dt)
        result = res[0].strip()
        format_str = "%Y-%m-%d" if len(result) == 8 else "%Y-%m-%d %H:%M"  # noqa: PLR2004
        return datetime.strptime(result, format_str).astimezone()
    except Exception as ex:
        raise InvalidDateTimeError(dt, ex) from ex


# HA's get_significant_states_with_session returns plain dicts when called
# with minimal_response=True. This helper safely extracts the state value
# regardless of which type we receive.
def _state_value(item: State | dict[str, Any]) -> str:
    return item.state if isinstance(item, State) else item["state"]


class EntityHistoryTool(BaseTool):
    """Tool for getting the significant change history of a device or entity."""

    name = "get_device_history_context"
    description = (
        "Where the `GetLiveContext` tool provides live device states, the `get_device_history_context` tool is used to retrieve the past (historic, previous) states of a device.\n"
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
        """Format a state record into an LLM-friendly dict with human-readable timestamps."""
        # as_dict() returns a ReadOnlyDict — copy to a mutable dict first.
        result = dict(state.as_dict() if isinstance(state, State) else state)

        # Convert ISO timestamps to human-readable format for the LLM.
        for key in ["last_changed", "last_updated"]:
            if key in result:
                dt = datetime.fromisoformat(result[key]).astimezone()
                result[key] = dt.strftime("%a %e %b %Y, %I:%M %p")

        return result

    @staticmethod
    def _compute_stats(
        raw_states: list[State | dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Compute summary statistics from raw state records.

        For numeric entities this returns min/max/avg so the LLM can
        understand the overall pattern without seeing every data point.
        Non-numeric entities (switches, sensors with string states) get
        only positional metadata — min/max/avg are omitted.
        """
        if not raw_states:
            return {}

        stats: dict[str, Any] = {
            "state_at_search_start": _state_value(raw_states[0]),
            "state_at_end": _state_value(raw_states[-1]),
            "total_data_points": len(raw_states),
        }

        # Try to parse as numeric. If any value fails, the entity is
        # non-numeric (e.g. on/off) and we skip min/max/avg entirely.
        numeric_values = []
        for s in raw_states:
            try:
                numeric_values.append(float(_state_value(s)))
            except (ValueError, TypeError):
                return stats

        stats["min"] = min(numeric_values)
        stats["max"] = max(numeric_values)
        stats["avg"] = sum(numeric_values) / len(numeric_values)

        return stats

    @staticmethod
    def _downsample(
        raw_states: list[State | dict[str, Any]], max_count: int
    ) -> list[State | dict[str, Any]]:
        """
        Select at most max_count states, preserving the shape of the data.

        Always keeps:
        - First and last data points
        - For numeric entities: the min and max values
        Remaining slots are filled by evenly distributing across the
        sorted time range so the LLM sees a representative sample.
        """
        if len(raw_states) <= max_count:
            return list(raw_states)

        n = len(raw_states)
        selected: set[int] = {0, n - 1}

        # Detect whether this entity is numeric; if so, preserve the
        # extreme values so the LLM can identify spikes and dips.
        numeric_values: dict[int, float] = {}
        is_numeric = True
        for i, s in enumerate(raw_states):
            try:
                numeric_values[i] = float(_state_value(s))
            except (ValueError, TypeError):
                is_numeric = False
                break

        if is_numeric:
            min_idx = min(numeric_values, key=numeric_values.get)
            max_idx = max(numeric_values, key=numeric_values.get)
            selected.add(min_idx)
            selected.add(max_idx)

        # Evenly distribute the remaining slot budget across the gap.
        remaining = max_count - len(selected)
        if remaining > 0:
            available = sorted(set(range(n)) - selected)
            avail_count = len(available)
            for j in range(remaining):
                idx = (j * avail_count) // remaining
                if idx < avail_count:
                    selected.add(available[idx])

        # Sort by index (== chronological order) before returning.
        sorted_indices = sorted(selected)
        return [raw_states[i] for i in sorted_indices]

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

        entity = find_entity_by_name(hass, entity_name)
        entity_id = entity.entity_id

        start_time = _to_datetime(start_time)
        end_time = _to_datetime(end_time)

        with recorder.util.session_scope(hass=hass, read_only=True) as session:
            result = await recorder.get_instance(hass).async_add_executor_job(
                lambda: history.get_significant_states_with_session(
                    hass,
                    session,
                    start_time,
                    end_time,
                    [entity_id],
                    None,
                    include_start_time_state=True,
                    significant_changes_only=True,
                    minimal_response=True,
                    no_attributes=True,
                )
            )

        results: dict[str, Any] = {}
        for sublist in result.values():
            if not sublist:
                continue
            results = self._process_entity_states(sublist, results)

        return results

    def _process_entity_states(
        self, sublist: list, results: dict[str, Any]
    ) -> dict[str, Any]:
        """Process a single entity's state list into LLM-friendly format."""
        start_state = sublist[0]
        remaining = sublist[1:]

        filtered = self._filter_unavailable(remaining)

        if not filtered:
            return self._build_empty_result(start_state, results)

        return self._build_result_with_stats(start_state, filtered, results)

    def _filter_unavailable(self, states: list) -> list[State | dict[str, Any]]:
        """Remove unavailable/unknown records that add no useful context."""
        return [s for s in states if _state_value(s) not in ("unavailable", "unknown")]

    def _build_empty_result(
        self,
        start_state: State | dict[str, Any],
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Return minimal result when no meaningful state changes exist."""
        results["stats"] = {
            "state_at_search_start": _state_value(start_state),
            "total_data_points": 1,
        }
        results["instruction"] = (
            "Answer the users question in a naturally-spoken manner"
        )
        return results

    def _build_result_with_stats(
        self,
        start_state: State | dict[str, Any],
        filtered: list[State | dict[str, Any]],
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Build result with summary stats and downsampled states."""
        stats = self._compute_stats(filtered)
        stats["state_at_search_start"] = _state_value(start_state)
        stats["total_data_points"] = len(filtered) + 1

        sampled = self._downsample(filtered, MAX_HISTORY_RESULTS)
        results["stats"] = stats
        results["sampled_states"] = [self.format_result(s) for s in sampled]
        results["instruction"] = (
            "Answer the users question in a naturally-spoken manner"
        )
        return results
