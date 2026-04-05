from homeassistant.core import HomeAssistant, State

def find_entity_by_name(hass: HomeAssistant, entity_name: str) -> State:
    """Find an entity by its name"""
    for state in hass.states.async_all():
        this_name = state.name.lower().strip()

        # TODO: aliases
        if this_name == entity_name:
            return state

    raise RuntimeError("Entity not found")