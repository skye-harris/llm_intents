"""Utility functions for entity lookups."""

from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import intent


class EntityNotFoundError(HomeAssistantError):
    """Exception raised when an entity is not found."""


def find_entity_by_name(hass: HomeAssistant, entity_name: str) -> State:
    """Find an entity by its name or aliases."""
    entity_name_norm = entity_name.lower().strip()

    for state in hass.states.async_all():
        entity_entry = er.async_get(hass).async_get(state.entity_id)
        names = intent.async_get_entity_aliases(hass, entity_entry, state=state)
        check_names = [state.entity_id, *names]
        for name in check_names:
            if name.lower().strip() == entity_name_norm:
                return state

    raise EntityNotFoundError
