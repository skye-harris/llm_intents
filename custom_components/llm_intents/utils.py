from homeassistant.core import HomeAssistant, State


def find_entity_by_name(hass: HomeAssistant, entity_name: str) -> State:
    for state in hass.states.async_all():
        if state.name.lower() == entity_name:
            return state

    raise RuntimeError("Entity not found")
