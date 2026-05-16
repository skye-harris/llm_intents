"""Subclass of AssistAPI with additional customisation."""

import logging

from homeassistant.components.intent import async_device_supports_timers
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    floor_registry as fr,
)
from homeassistant.helpers import (
    llm,
    template,
)
from homeassistant.helpers.llm import AssistAPI, LLMContext, Tool

from .const import (
    CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE,
    CONF_HOME_CONTROL_DISABLED_TOOLS,
    CONF_HOME_CONTROL_PROMPT_TEMPLATE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class HomeControlAPI(AssistAPI):
    """Subclass and modify Assist."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Init the class."""
        super().__init__(hass)
        self.name = "Home Control"
        self.id = "HomeControl"

    @callback
    def _async_get_api_prompt(
        self, llm_context: llm.LLMContext, exposed_entities: dict | None
    ) -> str:
        """Build the prompt with a jinja template."""
        config_data = self.hass.data[DOMAIN].get("config", {})
        entry = next(iter(self.hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}
        prompt_template = config_data.get(
            CONF_HOME_CONTROL_PROMPT_TEMPLATE, CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE
        )
        exposed_entities = (
            list(exposed_entities["entities"].values()) if exposed_entities else []
        )

        supports_timers = llm_context.device_id and async_device_supports_timers(
            self.hass, llm_context.device_id
        )

        floor: fr.FloorEntry | None = None
        area: ar.AreaEntry | None = None

        if llm_context.device_id:
            device_reg = dr.async_get(self.hass)
            device = device_reg.async_get(llm_context.device_id)

            if device:
                area_reg = ar.async_get(self.hass)
                if device.area_id and (area := area_reg.async_get_area(device.area_id)):
                    floor_reg = fr.async_get(self.hass)
                    if area.floor_id:
                        floor = floor_reg.async_get_floor(area.floor_id)

        return (
            template.Template(
                prompt_template,
                self.hass,
            )
            .async_render(
                {
                    "exposed_entities": exposed_entities,
                    "floor": floor,
                    "area": area,
                    "supports_timers": supports_timers,
                },
                parse_result=False,
            )
            .strip()
        )

    def _async_get_tools(
        self, llm_context: LLMContext, exposed_entities: dict | None
    ) -> list[Tool]:
        """Return a list of tools, filtered per our config settings."""
        config_data = self.hass.data[DOMAIN].get("config", {})
        entry = next(iter(self.hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}

        tools = super()._async_get_tools(llm_context, exposed_entities)

        # Filter by the disabled tools rule
        return [
            tool
            for tool in tools
            if tool.name not in config_data.get(CONF_HOME_CONTROL_DISABLED_TOOLS, [])
        ]
