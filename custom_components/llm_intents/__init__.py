from .brave_search import BraveSearch
from .google_places import GooglePlaces
from .wikipedia_search import WikipediaSearch

from homeassistant.helpers import intent
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
import logging

from .const import (
    DOMAIN,
    CONF_BRAVE_INTENT,
    CONF_BRAVE_API_KEY,
    CONF_BRAVE_NUM_RESULTS,
    CONF_BRAVE_COUNTRY_CODE,
    CONF_BRAVE_LATITUDE,
    CONF_BRAVE_LONGITUDE,
    CONF_BRAVE_TIMEZONE,
    CONF_BRAVE_POST_CODE,
    CONF_GOOGLE_PLACES_INTENT,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_WIKIPEDIA_INTENT,
    CONF_WIKIPEDIA_NUM_RESULTS,
)


_LOGGER = logging.getLogger(__name__)


PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_BRAVE_INTENT): vol.Schema(
            {
                vol.Required(CONF_BRAVE_API_KEY): cv.string,
                vol.Optional(CONF_BRAVE_NUM_RESULTS, default=2): cv.positive_int,
                vol.Optional(CONF_BRAVE_COUNTRY_CODE): cv.string,
                vol.Optional(CONF_BRAVE_LATITUDE): cv.latitude,
                vol.Optional(CONF_BRAVE_LONGITUDE): cv.longitude,
                vol.Optional(CONF_BRAVE_TIMEZONE): cv.string,
                vol.Optional(CONF_BRAVE_POST_CODE): cv.string,
            }
        ),
        vol.Optional(CONF_GOOGLE_PLACES_INTENT): vol.Schema(
            {
                vol.Required(CONF_GOOGLE_PLACES_API_KEY): cv.string,
                vol.Optional(
                    CONF_GOOGLE_PLACES_NUM_RESULTS, default=2
                ): cv.positive_int,
            }
        ),
        vol.Optional(CONF_WIKIPEDIA_INTENT): vol.Any(
            bool,
            vol.Schema(
                {
                    vol.Optional(
                        CONF_WIKIPEDIA_NUM_RESULTS, default=1
                    ): cv.positive_int,
                }
            ),
        ),
    },
)


INTENTS = [
    (CONF_BRAVE_INTENT, BraveSearch),
    (CONF_GOOGLE_PLACES_INTENT, GooglePlaces),
    (CONF_WIKIPEDIA_INTENT, WikipediaSearch),
]


async def async_setup(hass, config):
    my_config = config.get(DOMAIN)
    if not my_config:
        return True

    my_config = my_config[0]

    for intent_key, intent_cls in INTENTS:
        if intent_key not in my_config:
            continue

        intent_config = my_config[intent_key]

        if not intent_config:
            continue

        if intent_config is True:
            intent_config = {}

        intent.async_register(hass, intent_cls(intent_config))

    return True
