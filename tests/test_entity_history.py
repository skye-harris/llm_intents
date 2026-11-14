"""Tests for entity history tool."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.llm import ToolResult

from custom_components.llm_intents.entity_history import (
    MAX_DURATION_STATES,
    MAX_HISTORY_RESULTS,
    EntityHistoryTool,
    _state_value,
    _to_datetime,
)
from custom_components.llm_intents.utils import EntityNotFoundError


def _make_states(
    entity_id: str,
    count: int,
    base_time: datetime,
    value_fn: Callable[[int], str],
    interval_seconds: int = 18,
) -> list[State]:
    return [
        State(
            entity_id,
            value_fn(i),
            last_changed=base_time + timedelta(seconds=i * interval_seconds),
            last_updated=base_time + timedelta(seconds=i * interval_seconds),
        )
        for i in range(count)
    ]


@pytest.fixture
def mock_recorder() -> tuple[MagicMock, MagicMock]:
    """Return mocked recorder components."""
    with (
        patch(
            "custom_components.llm_intents.entity_history.find_entity_by_name",
        ) as mock_find,
        patch(
            "custom_components.llm_intents.entity_history.recorder.util.session_scope",
        ) as mock_scope,
        patch(
            "custom_components.llm_intents.entity_history.recorder.get_instance",
        ) as mock_get_instance,
        patch(
            "custom_components.llm_intents.entity_history.async_get_exposed_entities",
            new=MagicMock(return_value={}),
        ),
    ):
        mock_session = MagicMock()
        mock_scope.return_value.__enter__.return_value = mock_session
        yield mock_find, mock_get_instance


# ---------------------------------------------------------------------------
# Integration tests — downsampling behavior
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "value_fn", "expected_sampled", "expected_total", "expect_numeric_stats"),
    [
        # High-frequency sensor: 200 points downsampled to MAX_HISTORY_RESULTS
        (
            200,
            lambda i: str(22.0 + (i % 10) * 0.1),
            MAX_HISTORY_RESULTS,
            200,
            True,
        ),
        # Low-frequency entity: 6 points, no downsampling
        (
            6,
            lambda i: str(21.0 + i),
            5,
            6,
            True,
        ),
        # Non-numeric entity: skips numeric stats but caps results
        (
            50,
            lambda i: "on" if i % 2 == 0 else "off",
            MAX_HISTORY_RESULTS,
            50,
            False,
        ),
    ],
)
async def test_downsampling_behavior(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
    count: int,
    value_fn: Callable[[int], str],
    expected_sampled: int,
    expected_total: int,
    expect_numeric_stats: bool,
) -> None:
    """Test downsampling with high-frequency, low-frequency, and non-numeric entities."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.temperature"
    mock_find.return_value = State(entity_id, "22.0")

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _make_states(entity_id, count, base_time, value_fn)

    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Temperature",
                "area": "Kitchen",
                "domain": "sensor",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )
    assert isinstance(result, ToolResult)

    assert len(result.data["sampled_states"]) == expected_sampled
    assert result.data["stats"]["total_data_points"] == expected_total
    if expect_numeric_stats:
        assert "min" in result.data["stats"]
        assert "max" in result.data["stats"]
        assert "avg" in result.data["stats"]
        assert "min_max_delta" in result.data["stats"]
        assert "start_end_delta" in result.data["stats"]
    else:
        assert "min" not in result.data["stats"]
        assert "max" not in result.data["stats"]
        assert "avg" not in result.data["stats"]
        assert "min_max_delta" not in result.data["stats"]
        assert "start_end_delta" not in result.data["stats"]


# ---------------------------------------------------------------------------
# Integration tests — early return / no sampled states
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state_value", "remaining_states", "expect_empty_result"),
    [
        # All remaining states unavailable → empty result with start state
        (
            "unavailable",
            [State("sensor.test", "unavailable", last_changed=datetime.now(UTC))],
            False,
        ),
        # Single data point (start only) → empty result with start state
        (
            "25.0",
            [State("sensor.test", "25.0", last_changed=datetime.now(UTC))],
            False,
        ),
        # Empty history from recorder → empty dict
        (
            "0",
            [],
            True,
        ),
        # Start available, end unavailable → empty result with both states
        (
            "22.0",
            [
                State("sensor.test", "22.0", last_changed=datetime.now(UTC)),
                State(
                    "sensor.test",
                    "unavailable",
                    last_changed=datetime.now(UTC) + timedelta(seconds=18),
                ),
            ],
            False,
        ),
    ],
)
async def test_early_return_no_sampled_states(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
    state_value: str,
    remaining_states: list,
    expect_empty_result: bool,
) -> None:
    """Test early return when no meaningful state changes exist."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.test"
    mock_find.return_value = State(entity_id, state_value)

    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: remaining_states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Test",
                "area": "Kitchen",
                "domain": "sensor",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )
    assert isinstance(result, ToolResult)

    if expect_empty_result:
        assert result.data == {}
    else:
        assert "stats" in result.data
        assert "sampled_states" not in result.data
        assert result.data["stats"]["state_at_search_start"] == state_value
        if state_value == "22.0":
            assert result.data["stats"]["state_at_end"] == "unavailable"


# ---------------------------------------------------------------------------
# Integration tests — type handling (dict vs State)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_data", "description"),
    [
        (
            "all_dicts",
            "Plain dicts returned by minimal_response=True",
        ),
        (
            "mixed",
            "Mix of State objects and plain dicts",
        ),
    ],
)
async def test_type_handling(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
    raw_data: str,
    description: str,
) -> None:
    """Test handling of plain dicts and mixed State/dict results."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.temp"
    mock_find.return_value = State(entity_id, "22.0")

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    if raw_data == "all_dicts":
        raw = _make_states(entity_id, 100, base_time, lambda i: str(22.0 + i))
        data = [{"state": s.state} if isinstance(s, State) else s for s in raw]
    else:
        state_obj = State(
            entity_id,
            "25.0",
            last_changed=base_time + timedelta(hours=1),
            last_updated=base_time + timedelta(hours=1),
        )
        data = [state_obj, {"state": "22.0"}, {"state": "23.0"}, {"state": "24.0"}]

    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: data},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Temp",
                "area": "Kitchen",
                "domain": "sensor",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )
    assert isinstance(result, ToolResult)

    assert "stats" in result.data
    assert "min" in result.data["stats"]
    assert "max" in result.data["stats"]
    assert "min_max_delta" in result.data["stats"]
    assert "start_end_delta" in result.data["stats"]
    assert "sampled_states" in result.data


# ---------------------------------------------------------------------------
# Unit tests — _state_value helper
# ---------------------------------------------------------------------------


def test_state_value_helper() -> None:
    """Test that _state_value works with both State objects and dicts."""
    state_obj = State("sensor.test", "42.5")
    assert _state_value(state_obj) == "42.5"

    state_dict: dict[str, str] = {"state": "on"}
    assert _state_value(state_dict) == "on"


# ---------------------------------------------------------------------------
# Unit tests — _filter_unavailable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("states", "expected_count", "expected_values"),
    [
        # Mixed: some unavailable/unknown, some valid
        (
            [
                State("sensor.test", "22.0", last_changed=datetime.now(UTC)),
                State("sensor.test", "unavailable", last_changed=datetime.now(UTC)),
                State("sensor.test", "unknown", last_changed=datetime.now(UTC)),
                State("sensor.test", "23.0", last_changed=datetime.now(UTC)),
            ],
            2,
            ["22.0", "23.0"],
        ),
        # All filtered
        (
            [
                State("sensor.test", "unavailable", last_changed=datetime.now(UTC)),
                State("sensor.test", "unknown", last_changed=datetime.now(UTC)),
            ],
            0,
            [],
        ),
        # With dicts
        (
            [{"state": "22.0"}, {"state": "unavailable"}, {"state": "23.0"}],
            2,
            ["22.0", "23.0"],
        ),
        # Empty list
        ([], 0, []),
    ],
)
def test_filter_unavailable(
    states: list,
    expected_count: int,
    expected_values: list[str],
) -> None:
    """Test _filter_unavailable strips unavailable/unknown records."""
    tool = EntityHistoryTool({}, MagicMock())
    result = tool._filter_unavailable(states)
    assert len(result) == expected_count
    for i, val in enumerate(expected_values):
        assert _state_value(result[i]) == val


# ---------------------------------------------------------------------------
# Unit tests — _build_empty_result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start_state", "start_value", "last_state", "last_value"),
    [
        (State("sensor.test", "22.5"), "22.5", State("sensor.test", "23.0"), "23.0"),
        ({"state": "available"}, "available", {"state": "unavailable"}, "unavailable"),
    ],
)
def test_build_empty_result(
    start_state: State | dict[str, str],
    start_value: str,
    last_state: State | dict[str, str],
    last_value: str,
) -> None:
    """Test _build_empty_result returns minimal result with start and end state."""
    tool = EntityHistoryTool({}, MagicMock())
    results = {}
    result = tool._build_empty_result(start_state, last_state, results)
    assert "stats" in result
    assert "sampled_states" not in result
    assert result["stats"]["state_at_search_start"] == start_value
    assert result["stats"]["state_at_end"] == last_value
    assert result["stats"]["total_data_points"] == 1


# ---------------------------------------------------------------------------
# Unit tests — _build_result_with_stats
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "start_state",
        "filtered_count",
        "numeric",
        "expected_min",
        "expected_max",
        "expected_avg",
        "last_state_value",
    ),
    [
        # Numeric entity
        (
            State("sensor.test", "20.0"),
            10,
            True,
            20.0,
            29.0,
            24.5,
            "unavailable",
        ),
        # Non-numeric entity
        (
            State("switch.test", "off"),
            5,
            False,
            None,
            None,
            None,
            "unavailable",
        ),
    ],
)
def test_build_result_with_stats(
    start_state: State,
    filtered_count: int,
    numeric: bool,
    expected_min: float | None,
    expected_max: float | None,
    expected_avg: float | None,
    last_state_value: str,
) -> None:
    """Test _build_result_with_stats computes stats and downsamples."""
    tool = EntityHistoryTool({}, MagicMock())
    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    if numeric:
        filtered = [
            State(
                "sensor.test",
                str(20.0 + i),
                last_changed=base_time + timedelta(minutes=i),
                last_updated=base_time + timedelta(minutes=i),
            )
            for i in range(filtered_count)
        ]
    else:
        filtered = [
            State(
                "switch.test",
                "on" if i % 2 == 0 else "off",
                last_changed=base_time + timedelta(minutes=i),
                last_updated=base_time + timedelta(minutes=i),
            )
            for i in range(filtered_count)
        ]
    last_state = State(filtered[-1].entity_id, last_state_value)
    results = {}
    result = tool._build_result_with_stats(start_state, filtered, last_state, results)

    assert "stats" in result
    assert "sampled_states" in result
    assert result["stats"]["state_at_search_start"] == _state_value(start_state)
    assert result["stats"]["total_data_points"] == filtered_count + 1
    assert result["stats"]["state_at_end"] == last_state_value

    if numeric:
        assert result["stats"]["min"] == expected_min
        assert result["stats"]["max"] == expected_max
        assert result["stats"]["avg"] == expected_avg
        assert result["stats"]["min_max_delta"] == round(expected_max - expected_min, 2)
        assert result["stats"]["start_end_delta"] == round(
            expected_max - expected_min, 2
        )
    else:
        assert "min" not in result["stats"]
        assert "max" not in result["stats"]
        assert "avg" not in result["stats"]
        assert "min_max_delta" not in result["stats"]
        assert "start_end_delta" not in result["stats"]


# ---------------------------------------------------------------------------
# Unit tests — _process_entity_states
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sublist", "expect_sampled", "expect_total"),
    [
        # Has data → full result with sampled states
        (
            [
                State("sensor.test", "20.0", last_changed=datetime.now(UTC)),
                State(
                    "sensor.test",
                    "21.0",
                    last_changed=datetime.now(UTC) + timedelta(minutes=1),
                ),
                State(
                    "sensor.test",
                    "22.0",
                    last_changed=datetime.now(UTC) + timedelta(minutes=2),
                ),
            ],
            True,
            3,
        ),
        # All filtered → empty result with start state
        (
            [
                State("sensor.test", "20.0", last_changed=datetime.now(UTC)),
                State(
                    "sensor.test",
                    "unavailable",
                    last_changed=datetime.now(UTC) + timedelta(minutes=1),
                ),
                State(
                    "sensor.test",
                    "unknown",
                    last_changed=datetime.now(UTC) + timedelta(minutes=2),
                ),
            ],
            False,
            1,
        ),
        # Start only → empty result with start state
        (
            [State("sensor.test", "25.0", last_changed=datetime.now(UTC))],
            False,
            1,
        ),
    ],
)
def test_process_entity_states(
    sublist: list,
    expect_sampled: bool,
    expect_total: int,
) -> None:
    """Test _process_entity_states builds correct result."""
    tool = EntityHistoryTool({}, MagicMock())
    results = {}
    result = tool._process_entity_states(sublist, results)
    assert "stats" in result
    if expect_sampled:
        assert "sampled_states" in result
    else:
        assert "sampled_states" not in result
    assert result["stats"]["total_data_points"] == expect_total
    assert result["stats"]["state_at_search_start"] == _state_value(sublist[0])


# ---------------------------------------------------------------------------
# Unit tests — _downsample
# ---------------------------------------------------------------------------


def test_downsample_empty() -> None:
    """Test _downsample returns empty list for empty input."""
    tool = EntityHistoryTool({}, MagicMock())
    assert tool._downsample([], 10) == []


def test_downsample_under_limit() -> None:
    """Test _downsample returns all states when under the limit."""
    tool = EntityHistoryTool({}, MagicMock())
    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _make_states("sensor.test", 5, base_time, str)
    result = tool._downsample(states, 10)
    assert len(result) == 5


def test_downsample_preserves_extremes() -> None:
    """Test _downsample keeps first, last, min, and max indices."""
    tool = EntityHistoryTool({}, MagicMock())
    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    values = [20.0] * 50 + [10.0] + [30.0] + [21.0] * 48
    states = _make_states(
        "sensor.test",
        100,
        base_time,
        lambda i: str(values[i]),
    )
    result = tool._downsample(states, 30)
    result_values = [float(_state_value(s)) for s in result]
    assert min(result_values) == 10.0
    assert max(result_values) == 30.0
    assert len(result) <= 30


# ---------------------------------------------------------------------------
# Integration tests — area/domain filtering
# ---------------------------------------------------------------------------


async def test_async_call_ignores_non_exposed_entity(
    hass: HomeAssistant,
) -> None:
    """Test that non-exposed entities return an error ToolResult."""
    hass.states.async_set("sensor.temperature", "22.0")
    hass.states.async_set("light.living_room", "on")

    exposed_entities = {
        "light.living_room": {
            "names": "Living Room Light",
            "domain": "light",
            "areas": "Living Room",
        },
    }

    tool = EntityHistoryTool({}, hass)
    with patch(
        "custom_components.llm_intents.entity_history.async_get_exposed_entities",
        return_value=exposed_entities,
    ):
        result = await tool.async_call(
            hass,
            MagicMock(
                tool_args={
                    "name": "Temperature",
                    "area": "Kitchen",
                    "domain": "sensor",
                    "start_date_time": "2024-01-15 00:00",
                    "end_date_time": "2024-01-15 23:59",
                }
            ),
            MagicMock(assistant="test_assistant"),
        )
        assert isinstance(result, ToolResult)

    assert "error" in result.data


# ---------------------------------------------------------------------------
# Unit tests — _compute_state_durations
# ---------------------------------------------------------------------------


def test_state_durations_basic_split() -> None:
    """Durations are clamped to the window and summed per state."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = [
        # Changed before the window opened: clamped to the window start.
        State("sensor.test", "A", last_changed=base - timedelta(minutes=5)),
        State("sensor.test", "B", last_changed=base + timedelta(minutes=20)),
        State("sensor.test", "A", last_changed=base + timedelta(minutes=40)),
    ]
    result = tool._compute_state_durations(states, base, base + timedelta(hours=1))
    assert [entry["state"] for entry in result] == ["A", "B"]
    assert result[0]["total_seconds"] == 40 * 60
    assert result[0]["percent"] == pytest.approx(66.7)
    assert result[1]["total_seconds"] == 20 * 60
    assert result[1]["percent"] == pytest.approx(33.3)


def test_state_durations_include_unknown() -> None:
    """Unknown periods are real elapsed time and reported as their own state."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = [
        State("sensor.test", "home", last_changed=base),
        State("sensor.test", "unknown", last_changed=base + timedelta(minutes=30)),
        State("sensor.test", "home", last_changed=base + timedelta(minutes=45)),
    ]
    result = tool._compute_state_durations(states, base, base + timedelta(hours=1))
    by_state = {entry["state"]: entry for entry in result}
    assert by_state["home"]["total_seconds"] == 45 * 60
    assert by_state["unknown"]["total_seconds"] == 15 * 60


def test_state_durations_dict_records() -> None:
    """Dict records with ISO last_changed strings are supported."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = [
        {"state": "on", "last_changed": base.isoformat()},
        {
            "state": "off",
            "last_changed": (base + timedelta(minutes=10)).isoformat(),
        },
    ]
    result = tool._compute_state_durations(states, base, base + timedelta(minutes=30))
    by_state = {entry["state"]: entry for entry in result}
    assert by_state["on"]["total_seconds"] == 10 * 60
    assert by_state["off"]["total_seconds"] == 20 * 60


def test_state_durations_high_cardinality_skipped() -> None:
    """Numeric-style entities with many distinct states get no durations."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _make_states(
        "sensor.test",
        MAX_DURATION_STATES + 1,
        base,
        str,
        interval_seconds=60,
    )
    assert tool._compute_state_durations(states, base, base) == []


def test_state_durations_single_point_no_window() -> None:
    """A single record with no window bounds yields no durations."""
    tool = EntityHistoryTool({}, MagicMock())
    states = [State("sensor.test", "on", last_changed=datetime.now(UTC))]
    assert tool._compute_state_durations(states, None, None) == []


# ---------------------------------------------------------------------------
# Integration test — durations pick the long state, not the frequent one
# ---------------------------------------------------------------------------


async def test_state_durations_majority_by_time(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """
    state_durations must rank by elapsed time, not by number of changes.

    Mirrors a pet-location sensor: several short flips between two rooms,
    then one long stay in a third — the long stay is the correct answer
    to "where was it for most of the period?".
    """
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.pet_location"
    mock_find.return_value = State(entity_id, "Living Room")

    # Derive the base time from the tool's own parser so the state
    # timestamps and the search window share one timezone frame
    # regardless of the test runner's local timezone.
    base = _to_datetime("2024-01-15 00:00")
    states = [
        State(entity_id, "Living Room", last_changed=base),
        State(entity_id, "Basement", last_changed=base + timedelta(minutes=10)),
        State(entity_id, "Living Room", last_changed=base + timedelta(minutes=20)),
        State(entity_id, "Basement", last_changed=base + timedelta(minutes=30)),
        State(entity_id, "Master bedroom", last_changed=base + timedelta(hours=1)),
    ]
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Pet location",
                "area": "",
                "domain": "sensor",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 06:00",
            }
        ),
        MagicMock(),
    )
    assert isinstance(result, ToolResult)

    durations = result.data["stats"]["state_durations"]
    assert [entry["state"] for entry in durations] == [
        "Master bedroom",
        "Basement",
        "Living Room",
    ]
    assert durations[0]["total_seconds"] == 5 * 3600
    assert durations[0]["percent"] == pytest.approx(83.3)


def test_time_weighted_average_weights_by_duration() -> None:
    """A value held for 50 minutes outweighs one held for 10."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = [
        State("sensor.test", "20.0", last_changed=base),
        State("sensor.test", "30.0", last_changed=base + timedelta(minutes=50)),
    ]
    result = tool._compute_time_weighted_average(
        states, base, base + timedelta(hours=1)
    )
    # (20*50 + 30*10) / 60 = 21.67, not the plain mean of 25.0.
    assert result == pytest.approx(21.67)


def test_time_weighted_average_non_numeric() -> None:
    """Non-numeric entities have no time-weighted average."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = [
        State("sensor.test", "on", last_changed=base),
        State("sensor.test", "off", last_changed=base + timedelta(minutes=30)),
    ]
    assert (
        tool._compute_time_weighted_average(states, base, base + timedelta(hours=1))
        is None
    )


def test_time_weighted_average_unknown_start_not_extended() -> None:
    """A non-numeric first record is skipped, not back-filled."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = [
        State("sensor.test", "unknown", last_changed=base),
        State("sensor.test", "20.0", last_changed=base + timedelta(minutes=10)),
        State("sensor.test", "30.0", last_changed=base + timedelta(minutes=40)),
    ]
    result = tool._compute_time_weighted_average(
        states, base, base + timedelta(hours=1)
    )
    # 20 held 10:10-10:40 (30 min), 30 held 10:40-11:00 (20 min):
    # (20*30 + 30*20) / 50 = 24.0. Extending 20 back over the unknown
    # prefix would give 23.33 instead.
    assert result == pytest.approx(24.0)


def test_time_weighted_average_in_stats() -> None:
    """_process_entity_states attaches time_weighted_avg to the stats."""
    tool = EntityHistoryTool({}, MagicMock())
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    sublist = [
        State("sensor.test", "20.0", last_changed=base),
        State("sensor.test", "30.0", last_changed=base + timedelta(minutes=50)),
    ]
    result = tool._process_entity_states(sublist, {}, base, base + timedelta(hours=1))
    assert result["stats"]["time_weighted_avg"] == pytest.approx(21.67)


# ---------------------------------------------------------------------------
# Ranked resolver integration — entity_id, candidates, browse
# ---------------------------------------------------------------------------


async def test_async_call_includes_resolved_entity(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """A successful call names the entity it resolved to."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.temperature"
    mock_find.return_value = State(entity_id, "22.0")

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _make_states(entity_id, 6, base_time, lambda i: str(21.0 + i))
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Temperature",
                "domain": "sensor",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )
    assert result.error is not True
    assert result.data["entity_id"] == entity_id
    assert "stats" in result.data


async def test_async_call_not_found_returns_candidates(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """A failed resolution returns ranked candidates and a retry hint."""
    mock_find, _ = mock_recorder
    candidates = [
        {
            "entity_id": "sensor.dining_room_temperature",
            "name": "Dining Room Temperature",
            "domain": "sensor",
            "areas": "Dining Room",
            "score": 80.0,
        }
    ]
    mock_find.side_effect = EntityNotFoundError(
        "No exposed entity matched 'Dining Room Temp'", candidates=candidates
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Dining Room Temp",
                "domain": "sensor",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )
    assert result.error is True
    assert result.data["candidates"] == candidates
    assert "entity_id" in result.data["hint"]


async def test_async_call_unexposed_entity_id_returns_candidates(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """An entity_id that is not exposed fails with candidates, not a crash."""
    tool = EntityHistoryTool({}, hass)
    with patch(
        "custom_components.llm_intents.entity_history.find_entity_candidates",
        return_value=[{"entity_id": "sensor.other"}],
    ):
        result = await tool.async_call(
            hass,
            MagicMock(
                tool_args={
                    "entity_id": "sensor.secret",
                    "start_date_time": "2024-01-15 00:00",
                    "end_date_time": "2024-01-15 23:59",
                }
            ),
            MagicMock(),
        )
    assert result.error is True
    assert result.data["candidates"] == [{"entity_id": "sensor.other"}]


async def test_async_call_no_name_browses_candidates(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """No name and no entity_id returns a browse list of candidates."""
    tool = EntityHistoryTool({}, hass)
    browse = [{"entity_id": "sensor.kitchen_temperature", "domain": "sensor"}]
    with patch(
        "custom_components.llm_intents.entity_history.find_entity_candidates",
        return_value=browse,
    ) as mock_candidates:
        result = await tool.async_call(
            hass,
            MagicMock(
                tool_args={
                    "domain": "sensor",
                    "start_date_time": "2024-01-15 00:00",
                    "end_date_time": "2024-01-15 23:59",
                }
            ),
            MagicMock(),
        )
    assert result.error is True
    assert result.data["candidates"] == browse
    mock_candidates.assert_called_once()


# ---------------------------------------------------------------------------
# Threshold durations
# ---------------------------------------------------------------------------


def _timed_states(
    entity_id: str, spec: list[tuple[int, str]], base_time: datetime
) -> list[State]:
    """Build states at (offset_seconds, value) points from base_time."""
    return [
        State(
            entity_id,
            value,
            last_changed=base_time + timedelta(seconds=offset),
            last_updated=base_time + timedelta(seconds=offset),
        )
        for offset, value in spec
    ]


def test_threshold_duration_above_below_split() -> None:
    """Above/below totals are computed from segment durations, not samples."""
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _timed_states(
        "sensor.temperature",
        [(-300, "20.0"), (600, "30.0"), (2400, "25.0")],
        base,
    )
    result = EntityHistoryTool._compute_threshold_duration(
        states, base, base + timedelta(hours=1), 25.0
    )
    assert result is not None
    # 20 held 10:00-10:10 (below, first record clamped to window start),
    # 30 held 10:10-10:40 (above), 25 held 10:40-11:00 (equal: neither).
    assert result["above_seconds"] == 1800
    assert result["below_seconds"] == 600
    assert result["above_percent"] == 50.0
    assert result["below_percent"] == 16.7
    assert result["threshold"] == 25.0


def test_threshold_duration_unknown_counts_as_neither() -> None:
    """Unknown gaps are excluded from both sides and from the denominator."""
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _timed_states(
        "sensor.temperature",
        [(0, "30.0"), (1200, "unknown"), (2400, "10.0")],
        base,
    )
    result = EntityHistoryTool._compute_threshold_duration(
        states, base, base + timedelta(hours=1), 25.0
    )
    assert result is not None
    assert result["above_seconds"] == 1200
    assert result["below_seconds"] == 1200
    assert result["above_percent"] == 50.0
    assert result["below_percent"] == 50.0


def test_threshold_duration_non_numeric_returns_none() -> None:
    """A categorical entity has no threshold duration."""
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _timed_states("switch.lamp", [(0, "on"), (600, "off")], base)
    result = EntityHistoryTool._compute_threshold_duration(
        states, base, base + timedelta(hours=1), 25.0
    )
    assert result is None


def test_threshold_duration_dict_records() -> None:
    """Plain dict records (minimal_response) with ISO timestamps work."""
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = [
        {"state": "30.0", "last_changed": base.isoformat()},
        {
            "state": "10.0",
            "last_changed": (base + timedelta(minutes=30)).isoformat(),
        },
    ]
    result = EntityHistoryTool._compute_threshold_duration(
        states, base, base + timedelta(hours=1), 25.0
    )
    assert result is not None
    assert result["above_seconds"] == 1800
    assert result["below_seconds"] == 1800


def test_process_entity_states_adds_threshold_duration() -> None:
    """_process_entity_states attaches threshold stats when asked."""
    base = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _timed_states("sensor.temperature", [(0, "30.0"), (1800, "10.0")], base)
    tool = EntityHistoryTool({}, MagicMock())
    result = tool._process_entity_states(
        states, {}, base, base + timedelta(hours=1), 25.0
    )
    td = result["stats"]["threshold_duration"]
    assert td["above_seconds"] == 1800
    assert td["below_seconds"] == 1800


async def test_async_call_with_threshold(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """End to end: a threshold argument produces threshold stats."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.temperature"
    mock_find.return_value = State(entity_id, "22.0")

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _timed_states(entity_id, [(0, "30.0"), (1800, "10.0")], base_time)
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Temperature",
                "area": "Kitchen",
                "domain": "sensor",
                "threshold": 25.0,
                "start_date_time": "2024-01-15 10:00",
                "end_date_time": "2024-01-15 11:00",
            }
        ),
        MagicMock(),
    )
    assert result.data["stats"]["threshold_duration"]["threshold"] == 25.0


async def test_async_call_without_threshold_has_no_threshold_stats(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """Without a threshold argument, no threshold stats are attached."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.temperature"
    mock_find.return_value = State(entity_id, "22.0")

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _timed_states(entity_id, [(0, "30.0"), (1800, "10.0")], base_time)
    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "name": "Temperature",
                "area": "Kitchen",
                "domain": "sensor",
                "start_date_time": "2024-01-15 10:00",
                "end_date_time": "2024-01-15 11:00",
            }
        ),
        MagicMock(),
    )
    assert "threshold_duration" not in result.data["stats"]
