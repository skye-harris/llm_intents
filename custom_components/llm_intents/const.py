"""
Constants for the llm_intents custom component.

This module defines configuration keys and domain names for various intent
integrations.
"""

DOMAIN = "llm_intents"
SEARCH_API_NAME = "Search Services"

# Brave-specific constants

CONF_BRAVE_ENABLED = "brave_search_enabled"
CONF_BRAVE_API_KEY = "brave_api_key"
CONF_BRAVE_NUM_RESULTS = "brave_num_results"
CONF_BRAVE_COUNTRY_CODE = "brave_country_code"
CONF_BRAVE_LATITUDE = "brave_latitude"
CONF_BRAVE_LONGITUDE = "brave_longitude"
CONF_BRAVE_TIMEZONE = "brave_timezone"
CONF_BRAVE_POST_CODE = "brave_post_code"

# Google Places-specific constants

CONF_GOOGLE_PLACES_ENABLED = "google_places_enabled"
CONF_GOOGLE_PLACES_API_KEY = "google_places_api_key"
CONF_GOOGLE_PLACES_NUM_RESULTS = "google_places_num_results"

# Wikipedia-specific constants

CONF_WIKIPEDIA_ENABLED = "wikipedia_enabled"
CONF_WIKIPEDIA_NUM_RESULTS = "wikipedia_num_results"
