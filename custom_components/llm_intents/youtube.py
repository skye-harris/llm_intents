"""YouTube search tool for Home Assistant LLM integration."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool
from .cache import SQLiteCache
from .const import (
    CONF_PROVIDER_API_KEYS,
    DOMAIN,
    PROVIDER_GOOGLE,
)

_LOGGER = logging.getLogger(__name__)


class SearchYouTubeTool(BaseTool):
    """Tool for searching YouTube videos."""

    name = "search_youtube"

    description = "\n".join(
        [
            "Use this tool to search YouTube when the user requests or infers they want to:",
            "- Find a video to watch",
            "- Search for music, tutorials, or other video content",
            "- Play something on a TV or media player",
        ]
    )

    prompt_description = "\n".join(
        [
            "Use the `search_youtube` tool to find videos on YouTube:",
            "- Returns video titles, URLs, channel names, and descriptions.",
            "- Use this when the user wants to watch or play video content.",
        ]
    )

    response_directive = "\n".join(
        [
            "Use the search results to answer the user's query.",
            "If the user wants to play a video, use the play_video tool with the video URL.",
        ]
    )

    parameters = vol.Schema(
        {
            vol.Required(
                "query", description="The search query for YouTube videos"
            ): str,
            vol.Optional(
                "num_results",
                default=1,
                description="Number of videos to return (1-25). Use more when the user wants multiple options.",
            ): vol.All(int, vol.Range(min=1, max=25)),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        config_data = hass.data[DOMAIN].get("config", {})
        entry = next(iter(hass.config_entries.async_entries(DOMAIN)))
        config_data = {**config_data, **entry.options}

        query = tool_input.tool_args["query"]
        num_results = tool_input.tool_args.get("num_results", 1)

        provider_keys = config_data.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_GOOGLE, "")

        if not api_key:
            return {"error": "Google API key not configured"}

        try:
            session = async_get_clientsession(hass)

            cache = SQLiteCache()
            cache_params = {"query": query, "maxResults": num_results}
            cached_response = cache.get(__name__, cache_params)
            if cached_response:
                return cached_response

            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": num_results,
                "key": api_key,
            }

            async with session.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = []

                    for item in data.get("items", []):
                        video_id = item.get("id", {}).get("videoId")
                        snippet = item.get("snippet", {})

                        if video_id:
                            results.append(
                                {
                                    "title": snippet.get("title"),
                                    "url": f"https://www.youtube.com/watch?v={video_id}",
                                    "channel": snippet.get("channelTitle"),
                                    "description": snippet.get("description"),
                                    "published_at": snippet.get("publishedAt"),
                                }
                            )

                    if results:
                        cache.set(
                            __name__,
                            cache_params,
                            {
                                "results": results,
                                "instruction": self.response_directive,
                            },
                        )

                    return (
                        {"results": results, "instruction": self.response_directive}
                        if results
                        else {"result": "No videos found"}
                    )

                _LOGGER.error(
                    "YouTube search received HTTP %s error: %s",
                    resp.status,
                    await resp.text(),
                )
                return {"error": f"YouTube search error: {resp.status}"}

        except Exception:
            _LOGGER.exception("YouTube search error")
            return {"error": "Error searching YouTube"}
