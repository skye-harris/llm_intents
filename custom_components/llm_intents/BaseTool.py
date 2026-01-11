from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm


class BaseTool(llm.Tool):
    def __init__(self, config: dict, hass: HomeAssistant):
        super().__init__()
        self.config = config
        self.hass = hass
