"""
Constants for the llm_intents custom component.

This module defines configuration keys and domain names for various intent
integrations.
"""

DOMAIN = "llm_intents"
ADDON_NAME = "Tools for Assist"

SEARCH_API_NAME = "Search Services"
WEATHER_API_NAME = "Weather Forecast"

# SQLite Cache

CONF_CACHE_MAX_AGE = "cache_max_age"

SEARCH_SERVICES_PROMPT = "You may utilise the Search Services tools to lookup up-to-date information from the internet."

WEATHER_SERVICES_PROMPT = """
Use the Weather Services tools to access current weather and forecast data.
"""

# Search Providers
CONF_SEARCH_PROVIDER = "search_provider"
CONF_SEARCH_PROVIDER_NONE = ""
CONF_SEARCH_PROVIDER_BRAVE = "Brave"
CONF_SEARCH_PROVIDER_SEARXNG = "SearXNG"

CONF_SEARCH_PROVIDERS = {
    "": CONF_SEARCH_PROVIDER_NONE,
    "Brave": CONF_SEARCH_PROVIDER_BRAVE,
    "SearXNG": CONF_SEARCH_PROVIDER_SEARXNG,
}

# SearXNG-specific constants

CONF_SEARXNG_URL = "searxng_server_url"
CONF_SEARXNG_NUM_RESULTS = "searxng_num_results"

# Brave-specific constants

CONF_BRAVE_ENABLED = "brave_search_enabled"
CONF_BRAVE_API_KEY = "brave_api_key"
CONF_BRAVE_NUM_RESULTS = "brave_num_results"
CONF_BRAVE_COUNTRY_CODE = "brave_country_code"
CONF_BRAVE_LATITUDE = "brave_latitude"
CONF_BRAVE_LONGITUDE = "brave_longitude"
CONF_BRAVE_TIMEZONE = "brave_timezone"
CONF_BRAVE_POST_CODE = "brave_post_code"

CONF_BRAVE_COUNTRY_CODES = {
    "": "",
    "AR": "Argentina",
    "AU": "Australia",
    "AT": "Austria",
    "BE": "Belgium",
    "BR": "Brazil",
    "CA": "Canada",
    "CL": "Chile",
    "DK": "Denmark",
    "FI": "Finland",
    "FR": "France",
    "DE": "Germany",
    "GR": "Greece",
    "HK": "Hong Kong",
    "IN": "India",
    "ID": "Indonesia",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "MY": "Malaysia",
    "MX": "Mexico",
    "NL": "Netherlands",
    "NZ": "New Zealand",
    "NO": "Norway",
    "CN": "China",
    "PL": "Poland",
    "PT": "Portugal",
    "PH": "Philippines",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "ZA": "South Africa",
    "ES": "Spain",
    "SE": "Sweden",
    "CH": "Switzerland",
    "TW": "Taiwan",
    "TR": "Turkey",
    "GB": "United Kingdom",
    "US": "United States",
}

# Google Places-specific constants

CONF_GOOGLE_PLACES_ENABLED = "google_places_enabled"
CONF_GOOGLE_PLACES_API_KEY = "google_places_api_key"
CONF_GOOGLE_PLACES_NUM_RESULTS = "google_places_num_results"
CONF_GOOGLE_PLACES_LATITUDE = "google_places_latitude"
CONF_GOOGLE_PLACES_LONGITUDE = "google_places_longitude"
CONF_GOOGLE_PLACES_RADIUS = "google_places_radius"
CONF_GOOGLE_PLACES_RANKING = "google_places_rank_preference"

# Wikipedia-specific constants

CONF_WIKIPEDIA_ENABLED = "wikipedia_enabled"
CONF_WIKIPEDIA_NUM_RESULTS = "wikipedia_num_results"

# Weather constants

CONF_WEATHER_ENABLED = "weather_enabled"
CONF_DAILY_WEATHER_ENTITY = "weather_daily_entity"
CONF_HOURLY_WEATHER_ENTITY = "weather_hourly_entity"
CONF_WEATHER_DATA_INCLUDED = "weather_data_included"
CONF_WEATHER_DATA_PRECIPITATION = "weather_data_precipitation"
CONF_WEATHER_DATA_WIND_SPEED = "weather_data_wind_speed"

# Service defaults

SERVICE_DEFAULTS = {
    CONF_BRAVE_API_KEY: "",
    CONF_BRAVE_NUM_RESULTS: 2,
    CONF_BRAVE_LATITUDE: "",
    CONF_BRAVE_LONGITUDE: "",
    CONF_BRAVE_TIMEZONE: "",
    CONF_BRAVE_COUNTRY_CODE: "",
    CONF_BRAVE_POST_CODE: "",
    CONF_SEARXNG_URL: "",
    CONF_SEARXNG_NUM_RESULTS: 2,
    CONF_GOOGLE_PLACES_API_KEY: "",
    CONF_GOOGLE_PLACES_NUM_RESULTS: 2,
    CONF_GOOGLE_PLACES_LATITUDE: "",
    CONF_GOOGLE_PLACES_LONGITUDE: "",
    CONF_GOOGLE_PLACES_RADIUS: 5,
    CONF_GOOGLE_PLACES_RANKING: "Distance",
    CONF_WIKIPEDIA_NUM_RESULTS: 1,
    CONF_DAILY_WEATHER_ENTITY: None,
    CONF_HOURLY_WEATHER_ENTITY: None,
}
