"""Tests for entity history tool."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, State

from custom_components.llm_intents.entity_history import (
    MAX_HISTORY_RESULTS,
    EntityHistoryTool,
    _state_value,
)


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
    """Test downsampling with high-frequency and low-frequency entities."""
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
                "entity_name": "Temperature",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )

    assert len(result["sampled_states"]) == expected_sampled
    assert result["stats"]["total_data_points"] == expected_total
    if expect_numeric_stats:
        assert "min" in result["stats"]
        assert "max" in result["stats"]
        assert "avg" in result["stats"]
    else:
        assert "min" not in result["stats"]
        assert "max" not in result["stats"]
        assert "avg" not in result["stats"]


async def test_downsample_preserves_min_max_and_order(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """Test downsampling preserves min/max values and chronological order."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "sensor.with_spike"
    mock_find.return_value = State(entity_id, "20.0")

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    values = [20.0] * 50 + [35.0] + [21.0] * 49
    states = _make_states(
        entity_id,
        100,
        base_time,
        lambda i: str(values[i]),
    )

    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "entity_name": "Sensor With Spike",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )

    assert result["stats"]["min"] == 20.0
    assert result["stats"]["max"] == 35.0
    sampled_states = [s["state"] for s in result["sampled_states"]]
    assert "35.0" in sampled_states
    timestamps = [s["last_changed"] for s in result["sampled_states"]]
    assert timestamps == sorted(timestamps), (
        "sampled_states must be in chronological order"
    )


# ---------------------------------------------------------------------------
# Integration tests — non-numeric entity
# ---------------------------------------------------------------------------


async def test_non_numeric_entity(
    mock_recorder: tuple[MagicMock, MagicMock],
    hass: HomeAssistant,
) -> None:
    """Test non-numeric entity skips numeric stats but caps results."""
    mock_find, mock_get_instance = mock_recorder
    entity_id = "switch.living_room_light"
    mock_find.return_value = State(entity_id, "off")

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    states = _make_states(
        entity_id,
        50,
        base_time,
        lambda i: "on" if i % 2 == 0 else "off",
    )

    mock_get_instance.return_value.async_add_executor_job = AsyncMock(
        return_value={entity_id: states},
    )

    tool = EntityHistoryTool({}, hass)
    result = await tool.async_call(
        hass,
        MagicMock(
            tool_args={
                "entity_name": "Living Room Light",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )

    assert len(result["sampled_states"]) == MAX_HISTORY_RESULTS
    assert "min" not in result["stats"]
    assert "max" not in result["stats"]
    assert "avg" not in result["stats"]
    assert result["stats"]["total_data_points"] == 50
    assert "state_at_search_start" in result["stats"]
    assert "state_at_end" in result["stats"]


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
                "entity_name": "Test",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )

    if expect_empty_result:
        assert result == {}
    else:
        assert "stats" in result
        assert "sampled_states" not in result
        assert result["stats"]["state_at_search_start"] == state_value


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
                "entity_name": "Temp",
                "start_date_time": "2024-01-15 00:00",
                "end_date_time": "2024-01-15 23:59",
            }
        ),
        MagicMock(),
    )

    assert "stats" in result
    assert "min" in result["stats"]
    assert "max" in result["stats"]
    assert "sampled_states" in result


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
    ("start_state", "start_value"),
    [
        (State("sensor.test", "22.5"), "22.5"),
        ({"state": "unavailable"}, "unavailable"),
    ],
)
def test_build_empty_result(
    start_state: State | dict[str, str],
    start_value: str,
) -> None:
    """Test _build_empty_result returns minimal result with start state."""
    tool = EntityHistoryTool({}, MagicMock())
    results = {}
    result = tool._build_empty_result(start_state, results)
    assert "stats" in result
    assert "sampled_states" not in result
    assert "instruction" in result
    assert result["stats"]["state_at_search_start"] == start_value
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
        ),
        # Non-numeric entity
        (
            State("switch.test", "off"),
            5,
            False,
            None,
            None,
            None,
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
    results = {}
    result = tool._build_result_with_stats(start_state, filtered, results)

    assert "stats" in result
    assert "sampled_states" in result
    assert "instruction" in result
    assert result["stats"]["state_at_search_start"] == _state_value(start_state)
    assert result["stats"]["total_data_points"] == filtered_count + 1
    assert result["stats"]["state_at_end"] == _state_value(filtered[-1])

    if numeric:
        assert result["stats"]["min"] == expected_min
        assert result["stats"]["max"] == expected_max
        assert result["stats"]["avg"] == expected_avg
    else:
        assert "min" not in result["stats"]
        assert "max" not in result["stats"]
        assert "avg" not in result["stats"]


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
