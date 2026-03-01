"""Base tool class, from which all others extend."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm


class BaseTool(llm.Tool):
    def __init__(self, config: dict, hass: HomeAssistant) -> None:
        """Init our tool."""
        super().__init__()
        self.config = config
        self.hass = hass

    @staticmethod
    def update_args(hass: HomeAssistant) -> None:
        pass
