"""
Constants for the wh40k_tools_for_assist custom component.

This module defines configuration keys and domain names for Warhammer 40k
lore integrations.
"""

DOMAIN = "wh40k_tools_for_assist"
ADDON_NAME = "WH40k Tools for Assist"

WH40K_API_NAME = "Warhammer 40k Lore"

# SQLite Cache

CONF_CACHE_MAX_AGE = "cache_max_age"

WH40K_SERVICES_PROMPT = """
You may use the Warhammer 40k lore tools to look up information about the Warhammer 40,000 universe.
- Use these tools for questions about WH40k factions, characters, battles, locations, and lore.
- The Lexicanum tool provides concise, curated information.
- The Fandom tool provides more detailed and comprehensive articles.
""".strip()

# Warhammer 40k Lexicanum-specific constants

CONF_WH40K_LEXICANUM_ENABLED = "wh40k_lexicanum_enabled"
CONF_WH40K_LEXICANUM_NUM_RESULTS = "wh40k_lexicanum_num_results"

# Warhammer 40k Fandom-specific constants

CONF_WH40K_FANDOM_ENABLED = "wh40k_fandom_enabled"
CONF_WH40K_FANDOM_NUM_RESULTS = "wh40k_fandom_num_results"

# Service defaults

SERVICE_DEFAULTS = {
    CONF_WH40K_LEXICANUM_NUM_RESULTS: 1,
    CONF_WH40K_FANDOM_NUM_RESULTS: 1,
}
