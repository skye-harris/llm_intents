"""Subclass of AssistAPI with additional customisation."""

import logging

from homeassistant.components.homeassistant.llm import async_get_exposed_entities
from homeassistant.components.intent import async_device_supports_timers
from homeassistant.components.llm import AssistAPI, async_get_tools
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

    def _get_config_data(self) -> dict:
        """Return the merged config data for this integration."""
        config_data = self.hass.data[DOMAIN].get("config", {})
        entry = next(iter(self.hass.config_entries.async_entries(DOMAIN)))
        return {**config_data, **entry.options}

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        """Return the API instance with a custom prompt and filtered tools."""
        llm_tools = await async_get_tools(self.hass, llm_context, llm.LLM_API_ASSIST)

        disabled_tools = self._get_config_data().get(
            CONF_HOME_CONTROL_DISABLED_TOOLS, []
        )
        tools = [tool for tool in llm_tools.tools if tool.name not in disabled_tools]

        return llm.APIInstance(
            api=self,
            api_prompt=self._async_get_api_prompt(llm_context),
            llm_context=llm_context,
            tools=tools,
            custom_serializer=llm.selector_serializer,
        )

    @callback
    def _async_get_api_prompt(self, llm_context: llm.LLMContext) -> str:
        """Build the prompt with a jinja template."""
        config_data = self._get_config_data()
        prompt_template = config_data.get(
            CONF_HOME_CONTROL_PROMPT_TEMPLATE, CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE
        )

        exposed_entities: list = []
        if llm_context.assistant:
            exposed_entities = list(
                async_get_exposed_entities(
                    self.hass, llm_context.assistant, include_state=False
                ).values()
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
