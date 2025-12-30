"""Tool for searching Warhammer 40k rules on Wahapedia."""

import logging

import voluptuous as vol
from bs4 import BeautifulSoup
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .cache import SQLiteCache
from .const import (
    CONF_WH40K_WAHAPEDIA_NUM_RESULTS,
    DOMAIN,
    WAHAPEDIA_FACTION_URL_TEMPLATE,
    WAHAPEDIA_FACTIONS,
    WAHAPEDIA_RULES_URLS,
)

_LOGGER = logging.getLogger(__name__)

# Cache TTL for rules content (24 hours in seconds)
CACHE_TTL_SECONDS = 86400


def normalize_faction_name(faction: str) -> str | None:
    """Normalize faction name to URL slug format."""
    if not faction:
        return None

    # Convert to lowercase and replace spaces with hyphens
    slug = faction.lower().strip().replace(" ", "-")

    # Check if it matches a known faction
    if slug in WAHAPEDIA_FACTIONS:
        return slug

    # Try partial match
    for known_faction in WAHAPEDIA_FACTIONS:
        if slug in known_faction or known_faction in slug:
            return known_faction

    return None


def extract_sections_from_html(html: str, source_url: str) -> list[dict]:
    """Extract sections from Wahapedia HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    sections = []

    # Find all heading elements that mark section starts
    headings = soup.find_all(["h1", "h2", "h3", "h4"])

    for heading in headings:
        title = heading.get_text(strip=True)
        if not title:
            continue

        # Collect content until next heading
        content_parts = []
        for sibling in heading.find_next_siblings():
            if sibling.name in ["h1", "h2", "h3", "h4"]:
                break
            text = sibling.get_text(strip=True)
            if text:
                content_parts.append(text)

        content = " ".join(content_parts)

        # Only include sections with actual content
        if content:
            sections.append(
                {
                    "title": title,
                    "content": content[:2000],  # Limit content length
                    "url": source_url,
                }
            )

    return sections


def search_sections(
    sections: list[dict], query: str, num_results: int
) -> list[dict]:
    """Search sections for query matches, prioritizing title matches."""
    query_lower = query.lower()
    title_matches = []
    content_matches = []

    for section in sections:
        title_lower = section["title"].lower()
        content_lower = section["content"].lower()

        if query_lower in title_lower:
            title_matches.append(section)
        elif query_lower in content_lower:
            content_matches.append(section)

    # Combine results, prioritizing title matches
    results = title_matches + content_matches
    return results[:num_results]


class SearchWh40kWahapediaTool(llm.Tool):
    """Tool for searching Warhammer 40k rules on Wahapedia."""

    name = "search_wh40k_wahapedia"
    description = (
        "Search Wahapedia for Warhammer 40k 10th edition game rules. "
        "Use this to look up game mechanics, phase rules (command, movement, shooting, "
        "charge, fight), stratagems, abilities, detachment rules, faction abilities, "
        "and other gameplay rules. Optionally specify a faction to search "
        "faction-specific rules like army rules, detachments, stratagems, and enhancements."
    )

    parameters = vol.Schema(
        {
            vol.Required(
                "query",
                description="The rule, ability, phase, or keyword to search for "
                "(e.g., 'shooting phase', 'stratagems', 'mortal wounds')",
            ): str,
            vol.Optional(
                "faction",
                description="Optional faction name to search faction-specific rules "
                "(e.g., 'astra-militarum', 'space-marines', 'Astra Militarum')",
            ): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Execute the Wahapedia search."""
        config_data = hass.data[DOMAIN].get("config", {})
        entry = next(iter(hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}

        query = tool_input.tool_args["query"]
        faction_input = tool_input.tool_args.get("faction")
        num_results = config_data.get(CONF_WH40K_WAHAPEDIA_NUM_RESULTS, 3)

        _LOGGER.info(
            "Wahapedia search requested for: %s (faction: %s)", query, faction_input
        )

        cache = SQLiteCache()

        try:
            session = async_get_clientsession(hass)
            all_sections = []

            # Determine which URLs to fetch
            if faction_input:
                faction_slug = normalize_faction_name(faction_input)
                if not faction_slug:
                    return {
                        "error": f"Unknown faction: {faction_input}. "
                        f"Known factions include: {', '.join(WAHAPEDIA_FACTIONS[:10])}..."
                    }
                urls = {
                    faction_slug: WAHAPEDIA_FACTION_URL_TEMPLATE.format(slug=faction_slug)
                }
            else:
                urls = WAHAPEDIA_RULES_URLS

            # Fetch and parse each URL
            for source_name, url in urls.items():
                cache_key = f"wahapedia_{source_name}"

                # Check cache first
                cached_sections = cache.get(
                    cache_key, {"url": url}, max_age=CACHE_TTL_SECONDS
                )
                if cached_sections:
                    all_sections.extend(cached_sections.get("sections", []))
                    continue

                # Fetch the page
                try:
                    async with session.get(url, timeout=30) as resp:
                        if resp.status != 200:
                            _LOGGER.warning(
                                "Wahapedia returned HTTP %s for %s", resp.status, url
                            )
                            continue

                        html = await resp.text()
                        sections = extract_sections_from_html(html, url)

                        # Cache the parsed sections
                        cache.set(cache_key, {"url": url}, {"sections": sections})
                        all_sections.extend(sections)

                except Exception as e:
                    _LOGGER.warning("Failed to fetch %s: %s", url, e)
                    continue

            if not all_sections:
                source = faction_input if faction_input else "core rules"
                return {"result": f"No content found for {source}"}

            # Search the sections
            results = search_sections(all_sections, query, num_results)

            if not results:
                source = faction_input if faction_input else "core rules"
                return {"result": f"No matches found for '{query}' in {source}"}

            return {"results": results}

        except Exception as e:
            _LOGGER.exception("Wahapedia search error")
            return {"error": f"Error searching Wahapedia: {e!s}"}
