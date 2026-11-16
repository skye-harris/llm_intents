"""Tests for find_entity_by_name utility function."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant, State

from custom_components.llm_intents.utils import (
    EntityNotFoundError,
    find_entity_by_name,
    find_entity_candidates,
)


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


# ---------------------------------------------------------------------------
# Failed lookups: candidates are suggested, never picked automatically
# ---------------------------------------------------------------------------


def test_partial_name_raises_with_ordered_candidates(
    hass_with_entities: HomeAssistant,
) -> None:
    """
    A partial name never resolves; it raises with candidates.

    The candidates come from the filtered set, ordered by plain name
    similarity: "Kitchen Temp" is closest to "Kitchen Temperature",
    and its candidate score is the raw name match (42.6) — the
    confirmed area adds nothing, because the score only orders the
    suggestions; nothing is ever picked automatically.
    """
    with pytest.raises(EntityNotFoundError) as excinfo:
        find_entity_by_name(
            hass_with_entities,
            "Kitchen Temp",
            area="Kitchen",
            domain="sensor",
            exposed_entities=_EXPOSED_ENTITIES,
        )
    candidates = excinfo.value.candidates
    assert candidates[0]["entity_id"] == "sensor.kitchen_temperature"
    assert candidates[0]["score"] == pytest.approx(42.6, abs=0.15)
    scores = [c["score"] for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_subset_name_raises_with_candidate(
    hass_with_entities: HomeAssistant,
) -> None:
    """A query naming a subset of an entity's name raises, suggesting it."""
    with pytest.raises(EntityNotFoundError) as excinfo:
        find_entity_by_name(
            hass_with_entities,
            "Garage",
            area=None,
            domain="switch",
            exposed_entities=_EXPOSED_ENTITIES,
        )
    assert excinfo.value.candidates[0]["entity_id"] == "switch.garage_door"


def test_strong_partial_name_is_not_picked() -> None:
    """
    Even a strong partial match is not picked automatically.

    "Kitchen Temperature Sensor Unit" is closest by a wide margin to
    "Kitchen Temperature Average", but it is not an exact match, so
    the lookup raises and suggests that entity as a candidate.
    """
    hass = MagicMock()
    hass.states.async_all.return_value = [
        State(
            "sensor.kitchen_temperature_average",
            "21.0",
            attributes={
                "friendly_name": "Kitchen Temperature Average",
                "device_class": "temperature",
            },
        ),
    ]
    exposed = {
        "sensor.kitchen_temperature_average": {
            "names": "Kitchen Temperature Average",
            "domain": "sensor",
            "areas": "Kitchen",
        },
    }

    def aliases(
        _h: object, _entry: object, state: State | None = None, **_k: object
    ) -> list[str]:
        return [state.attributes["friendly_name"]] if state is not None else []

    with (
        patch("custom_components.llm_intents.utils.er.async_get") as mock_get,
        patch(
            "custom_components.llm_intents.utils.intent.async_get_entity_aliases",
            side_effect=aliases,
        ),
    ):
        mock_get.return_value.async_get.return_value = MagicMock()
        with pytest.raises(EntityNotFoundError) as excinfo:
            find_entity_by_name(
                hass,
                "Kitchen Temperature Sensor Unit",
                area="Kitchen",
                domain="sensor",
                exposed_entities=exposed,
            )
    assert (
        excinfo.value.candidates[0]["entity_id"] == "sensor.kitchen_temperature_average"
    )


def test_exact_name_wrong_area_fails(hass_with_entities: HomeAssistant) -> None:
    """An exact name match still fails when the area filter is wrong."""
    with pytest.raises(EntityNotFoundError):
        find_entity_by_name(
            hass_with_entities,
            "Living Room Light",
            area="Kitchen",
            domain="light",
            exposed_entities=_EXPOSED_ENTITIES,
        )


def test_exact_name_wrong_domain_fails(hass_with_entities: HomeAssistant) -> None:
    """An exact name match still fails when the domain filter is wrong."""
    with pytest.raises(EntityNotFoundError):
        find_entity_by_name(
            hass_with_entities,
            "Living Room Light",
            area="Living Room",
            domain="sensor",
            exposed_entities=_EXPOSED_ENTITIES,
        )


def test_partial_name_wrong_area_fails(
    hass_with_entities: HomeAssistant,
) -> None:
    """A partial name is not rescued across areas; it still fails."""
    with pytest.raises(EntityNotFoundError):
        find_entity_by_name(
            hass_with_entities,
            "Kitchen Temp",
            area="Living Room",
            domain="sensor",
            exposed_entities=_EXPOSED_ENTITIES,
        )


def test_candidates_respect_filters(hass_with_entities: HomeAssistant) -> None:
    """Candidates never include entities outside the supplied filters."""
    with pytest.raises(EntityNotFoundError) as excinfo:
        find_entity_by_name(
            hass_with_entities,
            "Kitchen Temperature",
            domain="light",
            exposed_entities=_EXPOSED_ENTITIES,
        )
    assert all(c["domain"] == "light" for c in excinfo.value.candidates)
    assert "sensor.kitchen_temperature" not in {
        c["entity_id"] for c in excinfo.value.candidates
    }

    candidates = find_entity_candidates(
        hass_with_entities,
        "Temperature",
        domain="light",
        exposed_entities=_EXPOSED_ENTITIES,
    )
    assert "sensor.kitchen_temperature" not in {c["entity_id"] for c in candidates}


def test_candidates_helper(hass_with_entities: HomeAssistant) -> None:
    """find_entity_candidates orders the kitchen sensor first for a partial name."""
    candidates = find_entity_candidates(
        hass_with_entities,
        "Kitchen Temp",
        domain="sensor",
        exposed_entities=_EXPOSED_ENTITIES,
    )
    assert candidates
    assert candidates[0]["entity_id"] == "sensor.kitchen_temperature"
    assert "score" in candidates[0]


def test_browse_candidates_without_name(hass_with_entities: HomeAssistant) -> None:
    """With no name, candidates browse exposed entities by domain."""
    candidates = find_entity_candidates(
        hass_with_entities,
        None,
        domain="sensor",
        exposed_entities=_EXPOSED_ENTITIES,
    )
    assert [c["entity_id"] for c in candidates] == ["sensor.kitchen_temperature"]


def test_empty_name_raises_without_candidates(
    hass_with_entities: HomeAssistant,
) -> None:
    """An empty name matches nothing exactly and raises with no candidates."""
    with pytest.raises(EntityNotFoundError) as excinfo:
        find_entity_by_name(
            hass_with_entities,
            "",
            domain="sensor",
            exposed_entities=_EXPOSED_ENTITIES,
        )
    assert excinfo.value.candidates == []


def test_ambiguous_name_raises_with_candidates() -> None:
    """Two equally good matches are not silently picked; both are returned."""
    hass = MagicMock()
    hass.states.async_all.return_value = [
        State(
            "sensor.dining_room_temperature",
            "21.0",
            attributes={"friendly_name": "Dining Room Temperature"},
        ),
        State(
            "sensor.dining_room_humidity",
            "40",
            attributes={"friendly_name": "Dining Room Humidity"},
        ),
    ]
    exposed = {
        "sensor.dining_room_temperature": {
            "names": "Dining Room Temperature",
            "domain": "sensor",
            "areas": "Dining Room",
        },
        "sensor.dining_room_humidity": {
            "names": "Dining Room Humidity",
            "domain": "sensor",
            "areas": "Dining Room",
        },
    }

    def aliases(
        _h: object, _entry: object, state: State | None = None, **_k: object
    ) -> list[str]:
        return [state.attributes["friendly_name"]] if state is not None else []

    with (
        patch("custom_components.llm_intents.utils.er.async_get") as mock_get,
        patch(
            "custom_components.llm_intents.utils.intent.async_get_entity_aliases",
            side_effect=aliases,
        ),
    ):
        mock_get.return_value.async_get.return_value = MagicMock()
        with pytest.raises(EntityNotFoundError) as excinfo:
            find_entity_by_name(
                hass,
                "Dining Room",
                domain="sensor",
                exposed_entities=exposed,
            )

    candidate_ids = {c["entity_id"] for c in excinfo.value.candidates}
    assert candidate_ids == {
        "sensor.dining_room_temperature",
        "sensor.dining_room_humidity",
    }
