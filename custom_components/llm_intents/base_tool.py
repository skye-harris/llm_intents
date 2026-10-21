"""Base tool class, from which all others extend."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import DOMAIN


class BaseTool(llm.Tool):
    """Base tool class from which all others extend."""

    integration = DOMAIN

    def __init__(
        self,
        config: dict,
        hass: HomeAssistant,
        llm_context: llm.LLMContext | None = None,
    ) -> None:
        """Init our tool."""
        super().__init__()
        self.config = config
        self.hass = hass
        self.llm_context = llm_context
