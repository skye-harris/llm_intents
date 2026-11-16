"""Entity history tool."""

import logging
import re
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.components import recorder
from homeassistant.components.homeassistant.llm import async_get_exposed_entities
from homeassistant.components.recorder import history
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import llm
from homeassistant.helpers.llm import ToolResult

from .base_tool import BaseTool
from .utils import EntityNotFoundError, find_entity_by_name, find_entity_candidates

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

# Maximum number of distinct state values for which per-state total
# durations are computed. Categorical entities (location, presence,
# on/off) have a handful of states; numeric sensors can have hundreds
# of distinct values, where per-state durations are meaningless bulk —
# those keep the existing min/max/avg summary instead.
MAX_DURATION_STATES = 30


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


def _state_timestamp(item: State | dict[str, Any]) -> float | None:
    """
    Extract the last_changed time of a state record as epoch seconds.

    Handles State objects (datetime attribute) and the plain dicts
    returned with minimal_response=True, whose timestamp may be an ISO
    string or an epoch number depending on the HA version. Returns None
    when no usable timestamp is present.
    """
    raw: Any
    if isinstance(item, State):
        raw = item.last_changed
    else:
        raw = None
        for key in ("last_changed", "lc", "last_updated", "lu"):
            if key in item:
                raw = item[key]
                break
    if raw is None:
        return None
    try:
        if isinstance(raw, datetime):
            return raw.timestamp()
        if isinstance(raw, (int, float)):
            return float(raw)
        parsed = datetime.fromisoformat(str(raw))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.timestamp()
    except (ValueError, TypeError, OSError):
        return None


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
        "- If the user wants to know when a person left or arrived home.\n"
        "For entities with a limited set of distinct states (such as location or presence sensors), the result's stats also include `state_durations`: the total time spent in each state during the search period. Use those totals, rather than estimating from the sampled states, when answering how long a device was in a state or which state it was in for most of a period.\n"
        "For numeric entities, the stats also include `time_weighted_avg`: the average value weighted by how long each value was held. Prefer it over the plain `avg` when answering what the average value was over a period.\n"
        "Questions about a period — an average, a total, how long something lasted, or which state lasted longest — must be answered from this tool's results, never from a current live state.\n"
        "The entity name must be the exact name or alias of an exposed entity, as in Home Assistant itself, and `domain` and `area`, when given, are strict filters: an entity outside the requested area or in another domain will not be returned. If a call fails to resolve the entity, the error result lists the closest candidate entities that match the filters — retry the call using one candidate's `entity_id` rather than guessing another name. If you already know the entity_id (for example from a previous result), pass `entity_id` directly.\n"
        "If the user asks how long a numeric value spent above or below a level (for example, how long the temperature was above 25 degrees), pass that level as the `threshold` argument; the result's stats will then include `threshold_duration` with the computed time above and below the threshold. Use those totals rather than estimating from the sampled states.\n"
        "Example queries: `What time did the kitchen reach 25 degrees?` `When was the bedroom light turned off?` `What was the temperature outside at 8am this morning?` `How long was it above 25 degrees today?`"
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Optional(
                "name",
                description="The name of the entity or device to retrieve the history for. It must match an exposed entity's name or alias exactly; if a call fails, the error result lists candidate entities to retry with by `entity_id`. Omit only when passing `entity_id`.",
            ): str,
            vol.Optional(
                "entity_id",
                description="The exact entity_id of the entity to retrieve history for, as returned in a previous result's candidates. Preferred over `name` when known.",
            ): str,
            vol.Optional(
                "area",
                description="The area name or alias of the entity (case-insensitive). A strict filter: entities outside this area are not considered.",
            ): str,
            vol.Optional(
                "domain",
                description="The entity's domain (case-insensitive). A strict filter: entities in another domain are not considered.",
            ): str,
            vol.Optional(
                "threshold",
                description="A numeric level for a 'how long above/below' question. When given for a numeric entity, the result's stats include `threshold_duration`: the computed time the value spent above and below this level during the search period.",
            ): vol.Coerce(float),
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

        For numeric entities this returns min/max/avg, a range delta (min to
        max) and a trend delta (first to last value) so the LLM can understand
        the overall pattern without seeing every data point.
        Non-numeric entities (switches, sensors with string states) get
        only positional metadata — min/max/avg/delta are omitted.
        """
        if not raw_states:
            return {}

        stats: dict[str, Any] = {
            "state_at_search_start": _state_value(raw_states[0]),
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
        stats["avg"] = round(sum(numeric_values) / len(numeric_values), 2)
        stats["min_max_delta"] = round(stats["max"] - stats["min"], 2)
        stats["start_end_delta"] = round(numeric_values[-1] - numeric_values[0], 2)

        return stats

    @staticmethod
    def _compute_state_durations(
        states: list[State | dict[str, Any]],
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> list[dict[str, Any]]:
        """
        Compute the total time spent in each distinct state.

        Each record's state is taken to last until the next record's
        last_changed; the first record is clamped to the window start
        and the final record runs to the window end. Unlike the sampled
        states, this is computed from the full (unfiltered) sequence —
        'unknown'/'unavailable' periods are real elapsed time and are
        reported as their own entries so shares stay honest.

        Returns an empty list when durations would be meaningless bulk
        (more than MAX_DURATION_STATES distinct values, e.g. a numeric
        sensor) or cannot be derived from the records available.
        """
        points: list[tuple[float, str]] = []
        for item in states:
            ts = _state_timestamp(item)
            if ts is not None:
                points.append((ts, _state_value(item)))
        if not points:
            return []

        points.sort(key=lambda point: point[0])

        if len({value for _, value in points}) > MAX_DURATION_STATES:
            return []

        start_ts = (
            window_start.timestamp() if window_start is not None else points[0][0]
        )
        end_ts = window_end.timestamp() if window_end is not None else points[-1][0]

        totals: dict[str, float] = {}
        for i, (ts, value) in enumerate(points):
            segment_start = max(ts, start_ts)
            segment_end = points[i + 1][0] if i + 1 < len(points) else end_ts
            segment_end = min(segment_end, end_ts)
            if segment_end > segment_start:
                totals[value] = totals.get(value, 0.0) + (segment_end - segment_start)

        total_seconds = sum(totals.values())
        if total_seconds <= 0:
            return []

        return [
            {
                "state": value,
                "total_seconds": round(seconds),
                "total_minutes": round(seconds / 60, 1),
                "percent": round(seconds / total_seconds * 100, 1),
            }
            for value, seconds in sorted(
                totals.items(), key=lambda item: item[1], reverse=True
            )
        ]

    @staticmethod
    def _compute_time_weighted_average(
        states: list[State | dict[str, Any]],
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> float | None:
        """
        Compute the time-weighted average of a numeric entity.

        The plain `avg` stat weights every state change equally, so a
        brief spike counts as much as a value held for hours. Here each
        value is weighted by how long the entity held it: each record
        lasts until the next record, the first record is clamped to the
        window start, and the final record runs to the window end.

        The caller passes the sequence with unknown/unavailable records
        already removed, so a gap is attributed to the last known value
        (the same basis as the other summary stats). A non-numeric first
        record (e.g. the entity was unknown at the window start) is
        skipped without extending the next value back over it.

        Returns None when no time-weighted average can be derived.
        """
        points: list[tuple[float, float, bool]] = []
        for idx, item in enumerate(states):
            ts = _state_timestamp(item)
            if ts is None:
                continue
            try:
                value = float(_state_value(item))
            except (ValueError, TypeError):
                continue
            points.append((ts, value, idx == 0))
        if not points:
            return None

        points.sort(key=lambda point: point[0])

        start_ts = (
            window_start.timestamp() if window_start is not None else points[0][0]
        )
        end_ts = window_end.timestamp() if window_end is not None else points[-1][0]

        weighted_sum = 0.0
        total_seconds = 0.0
        for i, (ts, value, is_first) in enumerate(points):
            segment_start = max(ts, start_ts) if is_first else ts
            segment_end = points[i + 1][0] if i + 1 < len(points) else end_ts
            segment_end = min(segment_end, end_ts)
            if segment_end > segment_start:
                duration = segment_end - segment_start
                weighted_sum += value * duration
                total_seconds += duration

        if total_seconds <= 0:
            return None

        return round(weighted_sum / total_seconds, 2)

    @staticmethod
    def _compute_threshold_duration(
        states: list[State | dict[str, Any]],
        window_start: datetime | None,
        window_end: datetime | None,
        threshold: float,
    ) -> dict[str, Any] | None:
        """
        Compute how long a numeric entity spent above/below a threshold.

        Each record's value is taken to last until the next record; the
        first record is clamped to the window start and the final record
        runs to the window end. Computed from the full sequence, not the
        downsampled states. Records whose value is not numeric (unknown,
        unavailable, a sensor gap) count as NEITHER above nor below —
        the previous value is not extended over them — and the returned
        percentages are shares of the known-value time only. A value
        exactly equal to the threshold counts as neither above nor below.

        Returns None when no known-value time can be derived.
        """
        points: list[tuple[float, float | None]] = []
        for item in states:
            ts = _state_timestamp(item)
            if ts is None:
                continue
            try:
                value: float | None = float(_state_value(item))
            except (ValueError, TypeError):
                value = None
            points.append((ts, value))
        if not points:
            return None

        points.sort(key=lambda point: point[0])

        start_ts = (
            window_start.timestamp() if window_start is not None else points[0][0]
        )
        end_ts = window_end.timestamp() if window_end is not None else points[-1][0]

        above_seconds = 0.0
        below_seconds = 0.0
        known_seconds = 0.0
        for i, (ts, value) in enumerate(points):
            segment_start = max(ts, start_ts)
            segment_end = points[i + 1][0] if i + 1 < len(points) else end_ts
            segment_end = min(segment_end, end_ts)
            if segment_end <= segment_start or value is None:
                continue
            duration = segment_end - segment_start
            known_seconds += duration
            if value > threshold:
                above_seconds += duration
            elif value < threshold:
                below_seconds += duration

        if known_seconds <= 0:
            return None

        return {
            "threshold": threshold,
            "above_seconds": round(above_seconds),
            "above_minutes": round(above_seconds / 60, 1),
            "above_percent": round(above_seconds / known_seconds * 100, 1),
            "below_seconds": round(below_seconds),
            "below_minutes": round(below_seconds / 60, 1),
            "below_percent": round(below_seconds / known_seconds * 100, 1),
        }

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

    @staticmethod
    def _resolve_entity(
        hass: HomeAssistant,
        tool_args: dict[str, Any],
        exposed_entities: dict[str, dict[str, Any]],
    ) -> tuple[str, str]:
        """
        Resolve the requested entity to (entity_id, display name).

        An explicit entity_id wins and must be exposed. Otherwise the
        name is resolved by find_entity_by_name (exact match only);
        a miss raises EntityNotFoundError carrying the closest
        candidates from the filtered set. With neither, raises
        EntityNotFoundError carrying the exposed entities matching
        the area/domain filters as browse candidates.
        """
        entity_id_arg = tool_args.get("entity_id")
        entity_name = tool_args.get("name")
        area = tool_args.get("area")
        domain = tool_args.get("domain")

        if entity_id_arg:
            if entity_id_arg not in exposed_entities:
                msg = f"Entity '{entity_id_arg}' is not exposed"
                raise EntityNotFoundError(
                    msg,
                    candidates=find_entity_candidates(
                        hass,
                        entity_name or entity_id_arg,
                        domain,
                        area,
                        exposed_entities=exposed_entities,
                    ),
                )
            return entity_id_arg, exposed_entities[entity_id_arg].get(
                "names"
            ) or entity_id_arg

        if entity_name:
            entity = find_entity_by_name(
                hass,
                entity_name,
                exposed_entities=exposed_entities,
                area=area,
                domain=domain,
            )
            return entity.entity_id, entity.name or entity.entity_id

        msg = "No entity name or entity_id was given"
        raise EntityNotFoundError(
            msg,
            candidates=find_entity_candidates(
                hass,
                None,
                domain,
                area,
                exposed_entities=exposed_entities,
            ),
        )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> ToolResult:
        """Return state change history of the device entity."""
        threshold = tool_input.tool_args.get("threshold")
        if threshold is not None:
            try:
                threshold = float(threshold)
            except (ValueError, TypeError):
                threshold = None
        start_time = tool_input.tool_args.get("start_date_time")
        end_time = tool_input.tool_args.get("end_date_time")

        if not llm_context.assistant:
            err_msg = "No assistant context available for entity history"
            return ToolResult(data={"error": err_msg}, error=True)

        try:
            exposed_entities = async_get_exposed_entities(
                hass, llm_context.assistant, include_state=False
            )

            entity_id, resolved_name = self._resolve_entity(
                hass, tool_input.tool_args, exposed_entities
            )

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

            # The final state cannot have lasted beyond the present
            # moment, even when the requested end is in the future
            # (e.g. "until 23:59" asked mid-day).
            effective_end = min(end_time, datetime.now(end_time.tzinfo))

            results: dict[str, Any] = {}
            for sublist in result.values():
                if not sublist:
                    continue
                results = self._process_entity_states(
                    sublist, results, start_time, effective_end, threshold
                )

            if results:
                # Name the entity the history was resolved to, so the
                # choice is auditable — but keep an empty result empty.
                results = {
                    "entity_id": entity_id,
                    "entity_name": resolved_name,
                    **results,
                }

            return ToolResult(data=results)
        except EntityNotFoundError as err:
            return ToolResult(
                data={
                    "error": str(err),
                    "candidates": err.candidates,
                    "hint": (
                        "Retry the call with one candidate's exact "
                        "entity_id in the `entity_id` argument."
                    ),
                },
                error=True,
            )
        except Exception as e:
            _LOGGER.exception("Entity history encountered an error")
            return ToolResult(
                data={"error": f"Error retrieving entity history: {e!s}"}, error=True
            )

    def _process_entity_states(
        self,
        sublist: list,
        results: dict[str, Any],
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        threshold: float | None = None,
    ) -> dict[str, Any]:
        """Process a single entity's state list into LLM-friendly format."""
        start_state = sublist[0]
        remaining = sublist[1:]
        last_state = remaining[-1] if remaining else start_state

        filtered = self._filter_unavailable(remaining)

        if not filtered:
            result = self._build_empty_result(start_state, last_state, results)
        else:
            result = self._build_result_with_stats(
                start_state, filtered, last_state, results
            )

        # Durations are computed from the full sequence (including the
        # start record and any unknown/unavailable periods) so the LLM
        # can answer "how long" / "most of the period" questions from
        # computed totals instead of estimating over the sampled states.
        durations = self._compute_state_durations(sublist, window_start, window_end)
        if durations:
            result["stats"]["state_durations"] = durations

        # The time-weighted average uses the start record plus the
        # filtered sequence — the same basis as the other summary stats.
        time_weighted_avg = self._compute_time_weighted_average(
            [start_state, *filtered], window_start, window_end
        )
        if time_weighted_avg is not None:
            result["stats"]["time_weighted_avg"] = time_weighted_avg

        # Threshold durations are computed from the full sequence
        # (including the start record and any unknown/unavailable
        # periods) so "how long above/below X" questions are answered
        # from computed totals, not estimated over the sampled states.
        if threshold is not None:
            threshold_duration = self._compute_threshold_duration(
                sublist, window_start, window_end, threshold
            )
            if threshold_duration is not None:
                result["stats"]["threshold_duration"] = threshold_duration

        return result

    def _filter_unavailable(self, states: list) -> list[State | dict[str, Any]]:
        """Remove unavailable/unknown records that add no useful context."""
        return [s for s in states if _state_value(s) not in ("unavailable", "unknown")]

    def _build_empty_result(
        self,
        start_state: State | dict[str, Any],
        last_state: State | dict[str, Any],
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Return minimal result when no meaningful state changes exist."""
        results["stats"] = {
            "state_at_search_start": _state_value(start_state),
            "state_at_end": _state_value(last_state),
            "total_data_points": 1,
        }
        return results

    def _build_result_with_stats(
        self,
        start_state: State | dict[str, Any],
        filtered: list[State | dict[str, Any]],
        last_state: State | dict[str, Any],
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Build result with summary stats and downsampled states."""
        stats = self._compute_stats(filtered)
        stats["state_at_search_start"] = _state_value(start_state)
        stats["state_at_end"] = _state_value(last_state)
        stats["total_data_points"] = len(filtered) + 1

        sampled = self._downsample(filtered, MAX_HISTORY_RESULTS)
        results["stats"] = stats
        results["sampled_states"] = [self.format_result(s) for s in sampled]
        return results
