"""Tests for find_entity_by_name utility function."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, State

from custom_components.llm_intents.utils import EntityNotFoundError, find_entity_by_name


@pytest.fixture
def hass_with_entities(hass: HomeAssistant) -> HomeAssistant:
    """Return a HomeAssistant with mock states and entity registry."""
    states = [
        State("light.living_room", "on"),
        State("sensor.kitchen_temperature", "22.0"),
        State("switch.garage_door", "off"),
    ]

    class MockEntry:
        def __init__(self, entity_id: str, aliases: list[str]) -> None:
            self.entity_id = entity_id
            self.aliases = aliases

    registry = {
        "light.living_room": MockEntry(
            "light.living_room", ["Living Room Light", "Living Room"]
        ),
        "sensor.kitchen_temperature": MockEntry(
            "sensor.kitchen_temperature", ["Kitchen Temperature"]
        ),
        "switch.garage_door": MockEntry("switch.garage_door", ["Garage Door"]),
    }

    def get_aliases(_h: object, entry: object | None, **_kwargs: object) -> list[str]:
        if entry is None:
            return []
        return list(entry.aliases) if entry.aliases else [entry.entity_id]

    with (
        patch(
            "custom_components.llm_intents.utils.intent.async_get_entity_aliases",
            side_effect=get_aliases,
        ),
    ):
        for s in states:
            hass.states.async_set(s.entity_id, s.state, s.attributes)

        with patch("custom_components.llm_intents.utils.er.async_get") as mock_reg:
            mock_registry = MagicMock()
            mock_registry.async_get.side_effect = registry.get
            mock_reg.return_value = mock_registry
            yield hass


def test_find_by_entity_id(hass_with_entities: HomeAssistant) -> None:
    """Test finding an entity by its full entity_id."""
    result = find_entity_by_name(hass_with_entities, "light.living_room")
    assert result.entity_id == "light.living_room"
    assert result.state == "on"


def test_find_by_human_name(hass_with_entities: HomeAssistant) -> None:
    """Test finding an entity by its human-readable name."""
    result = find_entity_by_name(hass_with_entities, "Living Room Light")
    assert result.entity_id == "light.living_room"
    assert result.state == "on"


def test_find_by_alias(hass_with_entities: HomeAssistant) -> None:
    """Test finding an entity by one of its aliases."""
    result = find_entity_by_name(hass_with_entities, "Living Room")
    assert result.entity_id == "light.living_room"


def test_find_case_insensitive(hass_with_entities: HomeAssistant) -> None:
    """Test that entity name matching is case-insensitive."""
    result = find_entity_by_name(hass_with_entities, "LIVING ROOM LIGHT")
    assert result.entity_id == "light.living_room"

    result = find_entity_by_name(hass_with_entities, "living room light")
    assert result.entity_id == "light.living_room"

    result = find_entity_by_name(hass_with_entities, "LiViNg RoOm LiGhT")
    assert result.entity_id == "light.living_room"


def test_find_whitespace_stripped(hass_with_entities: HomeAssistant) -> None:
    """Test that leading/trailing whitespace is stripped from the search term."""
    result = find_entity_by_name(hass_with_entities, "  Living Room Light  ")
    assert result.entity_id == "light.living_room"

    result = find_entity_by_name(hass_with_entities, "\tKitchen Temperature\n")
    assert result.entity_id == "sensor.kitchen_temperature"


def test_find_not_found_raises(hass_with_entities: HomeAssistant) -> None:
    """Test that EntityNotFoundError is raised when no entity matches."""
    with pytest.raises(EntityNotFoundError):
        find_entity_by_name(hass_with_entities, "nonexistent_entity")


def test_find_not_found_case_insensitive(hass_with_entities: HomeAssistant) -> None:
    """Test that EntityNotFoundError is raised even with different casing."""
    with pytest.raises(EntityNotFoundError):
        find_entity_by_name(hass_with_entities, "NonExistent")


def test_find_no_entity_entry() -> None:
    """Test that entities without registry entries are still found by entity_id."""
    hass = MagicMock()
    hass.states.async_all.return_value = [
        State("light.unknown_entity", "on"),
    ]

    with (
        patch("custom_components.llm_intents.utils.er.async_get") as mock_get,
        patch(
            "custom_components.llm_intents.utils.intent.async_get_entity_aliases"
        ) as mock_aliases,
    ):
        mock_get.return_value.async_get.return_value = None
        mock_aliases.return_value = []

        result = find_entity_by_name(hass, "light.unknown_entity")
        assert result.entity_id == "light.unknown_entity"
        assert result.state == "on"


def test_find_multiple_entities_same_state(hass_with_entities: HomeAssistant) -> None:
    """Test that the first matching entity is returned."""
    result = find_entity_by_name(hass_with_entities, "Kitchen Temperature")
    assert result.entity_id == "sensor.kitchen_temperature"
    assert result.state == "22.0"
