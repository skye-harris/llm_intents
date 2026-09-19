"""Tests for the PlayVideoTool."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import AreaRegistry
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.entity_registry import EntityRegistry

from custom_components.llm_intents.play_media import (
    PlayVideoTool,
    get_video_capable_media_players,
    resolve_area_id,
)


def _tool_input(**args: Any) -> MagicMock:
    tool_input = MagicMock()
    tool_input.tool_args = args
    return tool_input


class _AreaEntry:
    """Plain area entry with real string attributes."""

    def __init__(self, aid: str, name: str) -> None:
        self.id = aid
        self.name = name


def _make_area_reg(areas: dict[str, str]) -> MagicMock:
    """Create a mock area registry. Mapping: id -> name."""
    area_reg = MagicMock(spec=AreaRegistry)
    entries = [_AreaEntry(aid, name) for aid, name in areas.items()]

    def get_area(x: str) -> _AreaEntry | None:
        for a in entries:
            if a.id == x or a.name == x:  # noqa: PLR1714
                return a
        return None

    area_reg.async_get_area = MagicMock(side_effect=get_area)
    area_reg.async_list_areas = MagicMock(return_value=entries)
    return area_reg


def _make_entity_reg(entities: dict[str, dict]) -> MagicMock:
    """Create a mock entity registry."""
    entity_reg = MagicMock(spec=EntityRegistry)
    entries: dict[str, MagicMock] = {}
    for eid, props in entities.items():
        entry = MagicMock()
        entry.entity_id = eid
        entry.device_id = props.get("device_id")
        entry.area_id = props.get("area_id")
        entries[eid] = entry
    entity_reg.entities = entries
    return entity_reg


def _make_device_reg(devices: dict[str, dict]) -> MagicMock:
    """Create a mock device registry."""
    device_reg = MagicMock(spec=DeviceRegistry)
    entries: dict[str, MagicMock] = {}
    for did, props in devices.items():
        dev = MagicMock()
        dev.area_id = props.get("area_id")
        entries[did] = dev

    def get_device(x: str) -> MagicMock | None:
        return entries.get(x)

    device_reg.async_get = MagicMock(side_effect=get_device)
    return device_reg


# ---------------------------------------------------------------------------
# resolve_area_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_val", "areas", "expected"),
    [
        # Exact ID match
        ("area_1", {"area_1": "Living Room"}, "area_1"),
        # Exact name match
        ("Living Room", {"area_1": "Living Room"}, "area_1"),
        # Case-insensitive name match
        ("living room", {"area_1": "Living Room"}, "area_1"),
        # Fuzzy: input is substring of area name
        ("Living", {"area_1": "Living Room"}, "area_1"),
        # Fuzzy: area name is substring of input
        ("Living Room TV", {"area_1": "Living Room"}, "area_1"),
        # Not found
        ("Nonexistent", {"area_1": "Living Room"}, None),
    ],
)
def test_resolve_area_id(input_val: str, areas: dict, expected: str | None) -> None:
    """Test area resolution: exact, case-insensitive, fuzzy, and missing."""
    hass = MagicMock()
    with patch(
        "custom_components.llm_intents.play_media.ar.async_get",
        return_value=_make_area_reg(areas),
    ):
        result = resolve_area_id(hass, input_val)
    assert result == expected


# ---------------------------------------------------------------------------
# get_video_capable_media_players
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "entities",
        "devices",
        "states",
        "area_id",
        "expected",
    ),
    [
        # TV in area -> included
        (
            {
                "media_player.tv": {
                    "device_id": "dev_1",
                    "area_id": "area_1",
                    "device_class": "tv",
                },
            },
            {"dev_1": {"area_id": "area_1"}},
            {"media_player.tv": {"device_class": "tv", "supported_features": 512}},
            "area_1",
            ["media_player.tv"],
        ),
        # Receiver in area -> included
        (
            {
                "media_player.receiver": {
                    "device_id": "dev_2",
                    "area_id": "area_1",
                    "device_class": "receiver",
                },
            },
            {"dev_2": {"area_id": "area_1"}},
            {
                "media_player.receiver": {
                    "device_class": "receiver",
                    "supported_features": 512,
                }
            },
            "area_1",
            ["media_player.receiver"],
        ),
        # Speaker in area -> skipped (audio-only)
        (
            {
                "media_player.speaker": {
                    "device_id": "dev_3",
                    "area_id": "area_1",
                    "device_class": "speaker",
                },
            },
            {"dev_3": {"area_id": "area_1"}},
            {
                "media_player.speaker": {
                    "device_class": "speaker",
                    "supported_features": 512,
                }
            },
            "area_1",
            [],
        ),
        # Entity without PLAY_MEDIA feature -> skipped
        (
            {
                "media_player.tv": {
                    "device_id": "dev_1",
                    "area_id": "area_1",
                    "device_class": "tv",
                },
            },
            {"dev_1": {"area_id": "area_1"}},
            {"media_player.tv": {"device_class": "tv", "supported_features": 0}},
            "area_1",
            [],
        ),
        # No device_class -> skipped
        (
            {
                "media_player.tv": {
                    "device_id": "dev_1",
                    "area_id": "area_1",
                    "device_class": None,
                },
            },
            {"dev_1": {"area_id": "area_1"}},
            {"media_player.tv": {"supported_features": 512}},
            "area_1",
            [],
        ),
        # No area_id -> returns all capable players
        (
            {
                "media_player.tv": {
                    "device_id": "dev_1",
                    "area_id": "area_1",
                    "device_class": "tv",
                },
                "media_player.receiver": {
                    "device_id": "dev_2",
                    "area_id": "area_2",
                    "device_class": "receiver",
                },
            },
            {
                "dev_1": {"area_id": "area_1"},
                "dev_2": {"area_id": "area_2"},
            },
            {
                "media_player.tv": {"device_class": "tv", "supported_features": 512},
                "media_player.receiver": {
                    "device_class": "receiver",
                    "supported_features": 512,
                },
            },
            None,
            ["media_player.tv", "media_player.receiver"],
        ),
        # Entity not in area -> excluded
        (
            {
                "media_player.tv": {
                    "device_id": "dev_1",
                    "area_id": "area_2",
                    "device_class": "tv",
                },
            },
            {"dev_1": {"area_id": "area_2"}},
            {"media_player.tv": {"device_class": "tv", "supported_features": 512}},
            "area_1",
            [],
        ),
        # Entity with no state -> skipped
        (
            {
                "media_player.tv": {
                    "device_id": "dev_1",
                    "area_id": "area_1",
                    "device_class": "tv",
                },
            },
            {"dev_1": {"area_id": "area_1"}},
            {},
            "area_1",
            [],
        ),
    ],
)
def test_get_video_capable_media_players(
    hass: HomeAssistant,
    entities: dict,
    devices: dict,
    states: dict,
    area_id: str | None,
    expected: list[str],
) -> None:
    """Test video-capable player discovery with various configurations."""
    mock_states = MagicMock()
    mock_states.get = MagicMock(
        side_effect=lambda eid: (
            MagicMock(attributes=states.get(eid, {})) if eid in states else None
        ),
    )
    hass.states = mock_states

    with (
        patch(
            "custom_components.llm_intents.play_media.er.async_get",
            return_value=_make_entity_reg(entities),
        ),
        patch(
            "custom_components.llm_intents.play_media.dr.async_get",
            return_value=_make_device_reg(devices),
        ),
    ):
        result = get_video_capable_media_players(hass, area_id)
    assert result == expected


# ---------------------------------------------------------------------------
# PlayVideoTool.async_call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "tool_args",
        "video_players",
        "area_id",
        "expected_success",
        "expected_error",
        "expected_target",
    ),
    [
        # Success via entity_id
        (
            {"video_url": "https://youtu.be/abc", "entity_id": "media_player.tv"},
            ["media_player.tv"],
            None,
            True,
            None,
            {"entity_id": "media_player.tv"},
        ),
        # Success via area
        (
            {"video_url": "https://youtu.be/abc", "area": "Living Room"},
            ["media_player.tv"],
            "area_1",
            True,
            None,
            {"entity_id": ["media_player.tv"]},
        ),
        # Success via device_id
        (
            {"video_url": "https://youtu.be/abc", "device_id": "dev_1"},
            [],
            None,
            True,
            None,
            {"device_id": "dev_1"},
        ),
        # No target, single player -> auto-selected
        (
            {"video_url": "https://youtu.be/abc"},
            ["media_player.tv"],
            None,
            True,
            None,
            {"entity_id": ["media_player.tv"]},
        ),
        # No target, no players -> error
        (
            {"video_url": "https://youtu.be/abc"},
            [],
            None,
            False,
            "No video-capable media players found in.",
            None,
        ),
        # No target, multiple players -> error
        (
            {"video_url": "https://youtu.be/abc"},
            ["media_player.tv", "media_player.receiver"],
            None,
            False,
            "Must specify at least one of: entity_id, area, or device_id",
            None,
        ),
        # Unresolved area -> error
        (
            {"video_url": "https://youtu.be/abc", "area": "Nowhere"},
            [],
            None,
            False,
            "Could not find area 'Nowhere'. Please check the area name.",
            None,
        ),
        # Area with no video players -> error
        (
            {"video_url": "https://youtu.be/abc", "area": "Kitchen"},
            [],
            "area_kitchen",
            False,
            "No video-capable media players found in area 'Kitchen'.",
            None,
        ),
        # entity_id + area -> combined
        (
            {
                "video_url": "https://youtu.be/abc",
                "entity_id": "media_player.tv",
                "area": "Living Room",
            },
            ["media_player.speaker"],
            "area_1",
            True,
            None,
            {"entity_id": ["media_player.tv", "media_player.speaker"]},
        ),
        # Service call raises exception -> error
        (
            {"video_url": "https://youtu.be/abc", "entity_id": "media_player.tv"},
            ["media_player.tv"],
            None,
            False,
            "Failed to play video on media_player.tv:",
            None,
        ),
    ],
)
async def test_async_call(
    hass: HomeAssistant,
    tool_args: dict,
    video_players: list[str],
    area_id: str | None,
    expected_success: bool,
    expected_error: str | None,
    expected_target: dict | None,
) -> None:
    """Test PlayVideoTool.async_call with various input combinations."""
    tool = PlayVideoTool({}, hass)

    # Mock area registry
    area_reg = MagicMock(spec=AreaRegistry)
    area_input = tool_args.get("area")
    if area_input and area_input != "Nowhere":
        area = MagicMock(id=area_id or "area_1", name=area_input)
        area_reg.async_get_area = MagicMock(return_value=area)
        area_reg.async_list_areas = MagicMock(return_value=[area])
    else:
        area_reg.async_get_area = MagicMock(return_value=None)
        area_reg.async_list_areas = MagicMock(return_value=[])

    service_error = (
        RuntimeError("service error")
        if expected_error and "Failed" in expected_error
        else None
    )

    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(side_effect=service_error)
    hass.services = mock_services

    with (
        patch(
            "custom_components.llm_intents.play_media.ar.async_get",
            return_value=area_reg,
        ),
        patch(
            "custom_components.llm_intents.play_media.get_video_capable_media_players",
            return_value=video_players,
        ),
    ):
        result = await tool.async_call(hass, _tool_input(**tool_args), MagicMock())

    if expected_success:
        assert result["success"] is True
        assert result["video_url"] == tool_args["video_url"]
        if expected_target:
            mock_services.async_call.assert_awaited_once()
            call_target = mock_services.async_call.call_args[1]["target"]
            assert call_target == expected_target
    else:
        assert result["success"] is False
        assert expected_error in result["error"]
