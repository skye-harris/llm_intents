"""
Constants for the llm_intents custom component.

This module defines configuration keys and domain names for various intent
integrations.
"""

DOMAIN = "llm_intents"

# Brave-specific constants

CONF_BRAVE_INTENT = "brave_search"
CONF_BRAVE_API_KEY = "brave_api_key"
CONF_BRAVE_NUM_RESULTS = "brave_num_results"
CONF_BRAVE_COUNTRY_CODE = "brave_country_code"
CONF_BRAVE_LATITUDE = "brave_latitude"
CONF_BRAVE_LONGITUDE = "brave_longitude"
CONF_BRAVE_TIMEZONE = "brave_timezone"
CONF_BRAVE_POST_CODE = "brave_post_code"

# Google Places–specific constants

CONF_GOOGLE_PLACES_INTENT = "google_places"
CONF_GOOGLE_PLACES_API_KEY = "google_places_api_key"
CONF_GOOGLE_PLACES_NUM_RESULTS = "google_places_num_results"

# Wikipedia–specific constants

CONF_WIKIPEDIA_INTENT = "wikipedia"
CONF_WIKIPEDIA_NUM_RESULTS = "wikipedia_num_results"
