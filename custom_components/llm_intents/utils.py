"""Utility functions for entity lookups."""

from typing import Any

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent


class EntityNotFoundError(HomeAssistantError):
    """Exception raised when an entity is not found."""


def find_entity_by_name(
    hass: HomeAssistant,
    entity_name: str,
    domain: str,
    area: str | None = None,
    *,
    exposed_entities: dict[str, dict[str, Any]],
) -> State:
    """Find an entity by its name or aliases."""
    entity_name_norm = entity_name.lower().strip()
    domain = domain.lower().strip()

    for state in hass.states.async_all():
        # Exposed entities filter
        if state.entity_id not in exposed_entities:
            continue

        # Domain filter
        if state.domain != domain:
            continue

        # Area filter
        if area is not None:
            area = area.lower().strip()
            entity_info = exposed_entities[state.entity_id]
            entity_areas = entity_info.get("areas")
            if entity_areas:
                area_list = [a.lower().strip() for a in entity_areas.split(", ")]
                if area not in area_list:
                    continue

        # Name matching
        entity_entry = er.async_get(hass).async_get(state.entity_id)
        names = intent.async_get_entity_aliases(hass, entity_entry, state=state)
        check_names = [state.entity_id, *names]
        for name in check_names:
            if name.lower().strip() == entity_name_norm:
                return state

    raise EntityNotFoundError
