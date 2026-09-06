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
        def __init__(
            self, entity_id: str, aliases: list[str], area_id: str | None = None
        ) -> None:
            self.entity_id = entity_id
            self.aliases = aliases
            self.area_id = area_id

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


_EXPOSED_ENTITIES = {
    "light.living_room": {
        "names": "Living Room Light",
        "domain": "light",
        "areas": "Living Room",
    },
    "sensor.kitchen_temperature": {
        "names": "Kitchen Temperature",
        "domain": "sensor",
        "areas": "Kitchen",
    },
    "switch.garage_door": {
        "names": "Garage Door",
        "domain": "switch",
        "areas": "Garage",
    },
}


@pytest.mark.parametrize(
    ("search_term", "area", "domain", "expected_entity_id", "expected_state"),
    [
        ("Living Room Light", "Living Room", "light", "light.living_room", "on"),
        ("Living Room", "Living Room", "light", "light.living_room", "on"),
        ("LIVING ROOM LIGHT", "Living Room", "light", "light.living_room", "on"),
        ("living room light", "Living Room", "light", "light.living_room", "on"),
        ("LiViNg RoOm LiGhT", "Living Room", "light", "light.living_room", "on"),
        ("  Living Room Light  ", "Living Room", "light", "light.living_room", "on"),
        (
            "\tKitchen Temperature\n",
            "Kitchen",
            "sensor",
            "sensor.kitchen_temperature",
            "22.0",
        ),
    ],
)
def test_find_success(
    hass_with_entities: HomeAssistant,
    search_term: str,
    area: str,
    domain: str,
    expected_entity_id: str,
    expected_state: str,
) -> None:
    """Test finding an entity by human name, alias, case variations, and whitespace."""
    result = find_entity_by_name(
        hass_with_entities,
        search_term,
        area=area,
        domain=domain,
        exposed_entities=_EXPOSED_ENTITIES,
    )
    assert result.entity_id == expected_entity_id
    assert result.state == expected_state


@pytest.mark.parametrize(
    ("search_term", "area", "domain"),
    [
        ("nonexistent_entity", "", ""),
        ("nonexistent_entity", "Living Room", "light"),
    ],
)
def test_find_not_found_raises(
    hass_with_entities: HomeAssistant,
    search_term: str,
    area: str,
    domain: str,
) -> None:
    """Test that EntityNotFoundError is raised when no entity matches."""
    with pytest.raises(EntityNotFoundError):
        find_entity_by_name(
            hass_with_entities,
            search_term,
            area=area,
            domain=domain,
            exposed_entities=_EXPOSED_ENTITIES,
        )


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

        result = find_entity_by_name(
            hass,
            "light.unknown_entity",
            area="",
            domain="light",
            exposed_entities={"light.unknown_entity": {"domain": "light"}},
        )
        assert result.entity_id == "light.unknown_entity"
        assert result.state == "on"


@pytest.mark.parametrize(
    ("search_term", "area", "domain", "exposed", "expect_error"),
    [
        # Domain match
        ("light.living_room", "Living Room", "light", _EXPOSED_ENTITIES, False),
        # Domain mismatch
        ("light.living_room", "Living Room", "sensor", _EXPOSED_ENTITIES, True),
        # Area mismatch
        ("light.living_room", "Kitchen", "light", _EXPOSED_ENTITIES, True),
        # Exposed entities filter: entity not in dict
        (
            "light.living_room",
            "Living Room",
            "light",
            {
                "light.living_room": {
                    "names": "Living Room Light",
                    "domain": "light",
                    "areas": "Living Room",
                },
            },
            False,
        ),
        (
            "sensor.kitchen_temperature",
            "Kitchen",
            "sensor",
            {
                "light.living_room": {
                    "names": "Living Room Light",
                    "domain": "light",
                    "areas": "Living Room",
                },
            },
            True,
        ),
        # Filtered out entirely
        (
            "sensor.kitchen_temperature",
            "Living Room",
            "sensor",
            _EXPOSED_ENTITIES,
            True,
        ),
    ],
)
def test_find_filters(
    hass_with_entities: HomeAssistant,
    search_term: str,
    area: str,
    domain: str,
    exposed: dict,
    expect_error: bool,
) -> None:
    """Test domain, area, and exposed_entities filtering."""
    if expect_error:
        with pytest.raises(EntityNotFoundError):
            find_entity_by_name(
                hass_with_entities,
                search_term,
                area=area,
                domain=domain,
                exposed_entities=exposed,
            )
    else:
        result = find_entity_by_name(
            hass_with_entities,
            search_term,
            area=area,
            domain=domain,
            exposed_entities=exposed,
        )
        assert result is not None
