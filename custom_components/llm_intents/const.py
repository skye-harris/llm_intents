"""
Constants for the llm_intents custom component.

This module defines configuration keys and domain names for various intent
integrations.
"""

DOMAIN = "llm_intents"
ADDON_NAME = "Tools for Assist"

SEARCH_API_NAME = "Search Services"
WEATHER_API_NAME = "Weather Forecast"
MEDIA_API_NAME = "Media Services"
BASIC_UTILITIES_API_NAME = "Basic Utilities"
HOME_CONTROL_API_NAME = "Home Control"

# SQLite Cache

CONF_CACHE_MAX_AGE = "cache_max_age"

SEARCH_SERVICES_PROMPT = "You may utilise the Search Services tools to lookup up-to-date information from the internet."

WEATHER_SERVICES_PROMPT = """
Use the Weather Services tools to access current weather and forecast data.
"""

MEDIA_SERVICES_PROMPT = """
Use the Media Services tools to play video content on media player devices.
"""

BASIC_UTILITIES_SERVICES_PROMPT = """
Use the Basic Utilities tools for calculations and unit conversions.
"""

# Basic Utilities constants

CONF_BASIC_UTILITIES_ENABLED = "basic_utilities_enabled"
CONF_CALCULATOR_ENABLED = "calculator_enabled"
CONF_UNIT_CONVERTER_ENABLED = "unit_converter_enabled"
CONF_DATE_INFO_ENABLED = "date_info_enabled"

# Search Providers
CONF_SEARCH_PROVIDER = "search_provider"
CONF_SEARCH_PROVIDER_BRAVE = "Brave"
CONF_SEARCH_PROVIDER_BRAVE_LLM = "Brave LLM Context"
CONF_SEARCH_PROVIDER_SEARXNG = "SearXNG"

CONF_SEARCH_PROVIDERS = {
    "Brave": CONF_SEARCH_PROVIDER_BRAVE,
    "Brave LLM Context": CONF_SEARCH_PROVIDER_BRAVE_LLM,
    "SearXNG": CONF_SEARCH_PROVIDER_SEARXNG,
}

# SearXNG-specific constants

CONF_SEARXNG_URL = "searxng_server_url"
CONF_SEARXNG_NUM_RESULTS = "searxng_num_results"

# Provider API keys - shared across tools using the same backend

CONF_PROVIDER_API_KEYS = "provider_api_keys"
PROVIDER_GOOGLE = "google"
PROVIDER_BRAVE = "brave"
PROVIDER_BRAVE_LLM = "brave_llm"

# Form field keys for provider API keys

CONF_GOOGLE_API_KEY = "google_api_key"
CONF_BRAVE_API_KEY = "brave_api_key"

# Brave-specific constants

CONF_BRAVE_ENABLED = "brave_search_enabled"
CONF_BRAVE_NUM_RESULTS = "brave_num_results"
CONF_BRAVE_COUNTRY_CODE = "brave_country_code"
CONF_BRAVE_LATITUDE = "brave_latitude"
CONF_BRAVE_LONGITUDE = "brave_longitude"
CONF_BRAVE_TIMEZONE = "brave_timezone"
CONF_BRAVE_POST_CODE = "brave_post_code"
CONF_BRAVE_MAX_SNIPPETS_PER_URL = "brave_max_snippets_per_url"
CONF_BRAVE_MAX_TOKENS_PER_URL = "brave_max_tokens_per_url"
CONF_BRAVE_CONTEXT_THRESHOLD_MODE = "brave_context_threshold_mode"

CONF_BRAVE_CONTEXT_THRESHOLD_MODES = {
    "strict": "Strict",
    "lenient": "Lenient",
    "balanced": "Balanced",
}

CONF_BRAVE_COUNTRY_CODES = {
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

# Google Routes-specific constants

CONF_GOOGLE_ROUTES_ENABLED = "google_routes_enabled"
CONF_GOOGLE_ROUTES_HOME_ADDRESS = "google_routes_home_address"
CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE = "google_routes_default_travel_mode"

CONF_GOOGLE_ROUTES_TRAVEL_MODES = {
    "DRIVE": "Driving",
    "WALK": "Walking",
    "BICYCLE": "Bicycle",
    "TRANSIT": "Public Transit",
    "TWO_WHEELER": "Motorcycle / Scooter",
}

# YouTube-specific constants

CONF_YOUTUBE_ENABLED = "youtube_enabled"

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
CONF_WEATHER_TEMPERATURE_SENSOR = "current_temperature_entity"

# Home Control constants
CONF_HOME_CONTROL_ENABLED = "home_control_enabled"
CONF_HOME_CONTROL_PROMPT_TEMPLATE = "home_control_prompt"
CONF_HOME_CONTROL_DISABLED_TOOLS = "home_control_disabled_tools"
CONF_HOME_CONTROL_DEFAULT_PROMPT_TEMPLATE = """
{%- if not exposed_entities %}
Only if the user wants to control a device, tell them to expose entities to their voice assistant in Home Assistant.
{%- else %}
When controlling Home Assistant always call the intent tools.
Use HassTurnOn to lock and HassTurnOff to unlock a lock.
When controlling a device, prefer passing just name and domain.
When controlling an area, prefer passing just area name and domain.

You ARE equipped to answer questions about the current state of the home using the `GetLiveContext` tool.
This is a primary function. Do not state you lack the functionality if the question requires live data.
If the user asks about device existence/type (e.g., "Do I have lights in the bedroom?"): Answer from the static context below.
If the user asks about the CURRENT state, value, or mode (e.g., "Is the lock locked?", "Is the fan on?", "What mode is the thermostat in?", "What is the temperature outside?"):
    1.  Recognize this requires live data.
    2.  You MUST call `GetLiveContext`. This tool will provide the needed real-time information (like temperature from the local weather, lock status, etc.).
    3.  Use the tool's response** to answer the user accurately (e.g., "The temperature outside is [value from tool].").
For general knowledge questions not about the home: Answer truthfully from internal knowledge.

{% if exposed_entities -%}
Static Context: An overview of the areas and the devices in this smart home:
{%- for entity in exposed_entities %}
  {{- "\n- names: " + entity.names }}
  {%- for key, value in entity.items() %}
    {%- if key != 'names' %}
      {{- "\n  " + key + ": " + value }}
    {%- endif %}
  {%- endfor %}
{%- endfor %}
{% endif %}

{%- set area_extra = "and all generic commands like 'turn on the lights' should target this area." %}
{%- if floor and area %}
    {{- "\nYou are in area " ~ area.name ~ " (floor " ~ floor.name ~ ") " ~ area_extra }}
{%- elif area %}
    {{- "\nYou are in area " ~ area.name ~ " " ~ area_extra }}
{%- else %}
    {{- "\nWhen a user asks to turn on all devices of a specific type, ask user to specify an area, unless there is only one device of that type." }}
{%- endif %}
{%- if not supports_timers %}
    {{- "\nThis device is not able to start timers." }}
{%- endif %}
{%- endif %}
""".strip()

# Service defaults

SERVICE_DEFAULTS = {
    CONF_BRAVE_NUM_RESULTS: 2,
    CONF_BRAVE_LATITUDE: "",
    CONF_BRAVE_LONGITUDE: "",
    CONF_BRAVE_TIMEZONE: "",
    CONF_BRAVE_COUNTRY_CODE: "",
    CONF_BRAVE_POST_CODE: "",
    CONF_BRAVE_MAX_SNIPPETS_PER_URL: 2,
    CONF_BRAVE_MAX_TOKENS_PER_URL: 1024,
    CONF_BRAVE_CONTEXT_THRESHOLD_MODE: "balanced",
    CONF_SEARXNG_URL: "",
    CONF_SEARXNG_NUM_RESULTS: 2,
    CONF_GOOGLE_PLACES_NUM_RESULTS: 2,
    CONF_GOOGLE_PLACES_LATITUDE: "",
    CONF_GOOGLE_PLACES_LONGITUDE: "",
    CONF_GOOGLE_PLACES_RADIUS: 5,
    CONF_GOOGLE_PLACES_RANKING: "Distance",
    CONF_GOOGLE_ROUTES_HOME_ADDRESS: "",
    CONF_GOOGLE_ROUTES_DEFAULT_TRAVEL_MODE: "DRIVE",
    CONF_WIKIPEDIA_NUM_RESULTS: 1,
    CONF_DAILY_WEATHER_ENTITY: None,
    CONF_HOURLY_WEATHER_ENTITY: None,
    CONF_WEATHER_TEMPERATURE_SENSOR: None,
    CONF_CALCULATOR_ENABLED: True,
    CONF_UNIT_CONVERTER_ENABLED: True,
    CONF_DATE_INFO_ENABLED: True,
}

# To satisfy ruff
CONFIG_VERSION_1 = 1
CONFIG_VERSION_2 = 2
