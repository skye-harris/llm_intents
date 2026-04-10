import logging
import voluptuous as vol

from homeassistant.util import yaml
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
from homeassistant.helpers.llm import AssistAPI, LLMContext, Tool, _get_exposed_entities, NO_ENTITIES_PROMPT, ToolInput
from homeassistant.util.json import JsonObjectType

from .const import (
    CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE,
    CONF_HOME_CONTROL_DISABLED_TOOLS,
    CONF_HOME_CONTROL_PROMPT_TEMPLATE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CustomAssistAPI(AssistAPI):
    """Subclass and modify Assist"""

    def __init__(self, hass: HomeAssistant) -> None:
        """Init the class."""
        super().__init__(hass)
        self.name = "Home Control"
        self.id = "HomeControl"

    @callback
    def _async_get_api_prompt(
        self, llm_context: llm.LLMContext, exposed_entities: dict | None
    ) -> str:
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
        config_data = self.hass.data[DOMAIN].get("config", {})
        entry = next(iter(self.hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}

        tools = super()._async_get_tools(llm_context, exposed_entities)

        # Swap out real live context tool for our filterable replacement tool
        tools = [
            tool
            for tool in tools
            if tool.name != "GetLiveContext"
        ]
        tools.append(GetFilterableLiveContextTool())

        # Now filter by the disabled tools rule
        tools = [
            tool
            for tool in tools
            if tool.name not in config_data.get(CONF_HOME_CONTROL_DISABLED_TOOLS, [])
        ]

        return tools


class GetFilterableLiveContextTool(Tool):
    """Tool for getting the current state of exposed entities.

    This returns state for all entities that have been exposed to
    the assistant. This is different than the GetState intent, which
    returns state for entities based on intent parameters.
    """

    name = "GetLiveContext"
    description = (
        "Provides real-time information about the CURRENT state, value, or mode of devices, sensors, entities, or areas.\n"
        "Use this tool for:\n"
        "1. Answering questions about current conditions (e.g., 'Is the light on?').\n"
        "2. As the first step in conditional actions (e.g., 'If the weather is rainy, turn off sprinklers' requires checking the weather first).\n"
        "You may filter for devices by any combination of arguments from the static context.\n"
        " - Prefer filtering by domain when searching for multiple devices of the same type"
    )

    parameters = vol.Schema(
        {
            vol.Optional("name", description="Filter details to a particular device"): str,
            vol.Optional("area", description="Filter details to a particular area"): str,
            vol.Optional("domain", description="Filter details to a particular domain"): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: ToolInput,
        llm_context: LLMContext,
    ) -> JsonObjectType:
        """Get the current state of exposed entities."""
        if llm_context.assistant is None:
            # Note this doesn't happen in practice since this tool won't be
            # exposed if no assistant is configured.
            return {"success": False, "error": "No assistant configured"}

        filter_name = tool_input.tool_args.get("name")
        filter_area = tool_input.tool_args.get("area")
        filter_domain = tool_input.tool_args.get("domain")

        exposed_entities = _get_exposed_entities(hass, llm_context.assistant)
        if not exposed_entities["entities"]:
            return {"success": False, "error": NO_ENTITIES_PROMPT}

        def filter_entity(entity: dict) -> bool:
            areas = entity.get("areas","").split(", ")
            names = entity.get("names", "").split(", ")
            domain = entity.get("domain")

            if filter_name and filter_name not in names:
                return False
            if filter_area and filter_area not in areas:
                return False
            if filter_domain and filter_domain != domain:
                return False
            return True

        exposed_entities = list(exposed_entities["entities"].values())
        exposed_entities = [entity for entity in exposed_entities if filter_entity(entity)]

        prompt = [
            "Live Context: An overview of the areas and the devices in this smart home:",
            yaml.dump(exposed_entities),
        ]
        return {
            "success": True,
            "result": "\n".join(prompt),
        }
