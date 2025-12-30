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
You may use the Warhammer 40k tools to look up information about the Warhammer 40,000 universe.
- Use the Lexicanum tool for concise, curated lore information.
- Use the Fandom tool for more detailed and comprehensive lore articles.
- Use the Wahapedia tool for 10th edition game rules, mechanics, stratagems, and faction-specific rules.
""".strip()

# Warhammer 40k Lexicanum-specific constants

CONF_WH40K_LEXICANUM_ENABLED = "wh40k_lexicanum_enabled"
CONF_WH40K_LEXICANUM_NUM_RESULTS = "wh40k_lexicanum_num_results"

# Warhammer 40k Fandom-specific constants

CONF_WH40K_FANDOM_ENABLED = "wh40k_fandom_enabled"
CONF_WH40K_FANDOM_NUM_RESULTS = "wh40k_fandom_num_results"

# Warhammer 40k Wahapedia-specific constants

CONF_WH40K_WAHAPEDIA_ENABLED = "wh40k_wahapedia_enabled"
CONF_WH40K_WAHAPEDIA_NUM_RESULTS = "wh40k_wahapedia_num_results"

# Core game rules URLs
WAHAPEDIA_RULES_URLS = {
    "quick-start-guide": "https://wahapedia.ru/wh40k10ed/the-rules/quick-start-guide/",
    "core-rules": "https://wahapedia.ru/wh40k10ed/the-rules/core-rules/",
}

# Faction rules URL template (slug = faction name with hyphens, e.g., "astra-militarum")
WAHAPEDIA_FACTION_URL_TEMPLATE = "https://wahapedia.ru/wh40k10ed/factions/{slug}/"

# Known factions (used for query matching)
WAHAPEDIA_FACTIONS = [
    "astra-militarum",
    "adeptus-mechanicus",
    "adeptus-custodes",
    "adepta-sororitas",
    "grey-knights",
    "space-marines",
    "blood-angels",
    "dark-angels",
    "black-templars",
    "space-wolves",
    "deathwatch",
    "imperial-knights",
    "imperial-agents",
    "chaos-space-marines",
    "death-guard",
    "thousand-sons",
    "world-eaters",
    "chaos-daemons",
    "chaos-knights",
    "aeldari",
    "drukhari",
    "harlequins",
    "votann",
    "tyranids",
    "genestealer-cults",
    "orks",
    "necrons",
    "tau-empire",
]

# Service defaults

SERVICE_DEFAULTS = {
    CONF_WH40K_LEXICANUM_NUM_RESULTS: 1,
    CONF_WH40K_FANDOM_NUM_RESULTS: 1,
    CONF_WH40K_WAHAPEDIA_NUM_RESULTS: 3,
}
