"""YouTube search tool for Tools for Assist."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.json import JsonObjectType

from .BaseTool import BaseTool
from .cache import SQLiteCache
from .const import (
    DOMAIN,
    PROVIDER_GOOGLE,
    get_provider_api_key,
)

_LOGGER = logging.getLogger(__name__)

YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3/search"


class SearchYouTubeTool(BaseTool):
    """Tool for searching YouTube videos."""

    name = "search_youtube"

    description = "\n".join(
        [
            "Use this tool to search YouTube when the user requests or infers they want to:",
            "- Find video(s) on a topic",
            "- Get a YouTube video URL for something",
        ]
    )

    prompt_description = "\n".join(
        [
            "Use the `search_youtube` tool to find videos on YouTube:",
            "- Returns video title, channel, URL, and thumbnail.",
        ]
    )

    response_directive = "\n".join(
        [
            "Use the search results to answer the user's query.",
            "Include the video URL when relevant so the user can watch.",
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
                description="Number of videos to return (1-4). Use more when the user wants multiple options.",
            ): vol.All(int, vol.Range(min=1, max=4)),
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
        api_key = get_provider_api_key(config_data, PROVIDER_GOOGLE)

        if not api_key:
            return {"error": "Google API key not configured for YouTube search"}

        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": num_results,
            "key": api_key,
        }

        try:
            cache = SQLiteCache()
            cached_response = cache.get(__name__, params)
            if cached_response:
                return cached_response

            session = async_get_clientsession(hass)
            async with session.get(
                YOUTUBE_API_BASE_URL, params=params, timeout=10
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error("YouTube API error %s: %s", resp.status, error_text)
                    return {
                        "error": "Failed to search YouTube. Check API key and ensure YouTube Data API v3 is enabled."
                    }

                data = await resp.json()

        except Exception as e:
            _LOGGER.error("YouTube search error: %s", e)
            return {"error": "Failed to search YouTube. Please try again later."}

        items = data.get("items", [])
        if not items:
            return {"result": "No videos found for the given query"}

        results = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            thumbnails = snippet.get("thumbnails", {})

            results.append(
                {
                    "videoId": video_id,
                    "title": snippet.get("title"),
                    "channelTitle": snippet.get("channelTitle"),
                    "publishedAt": snippet.get("publishedAt"),
                    "description": snippet.get("description"),
                    "thumbnail": thumbnails.get("default", {}).get("url")
                    if thumbnails
                    else None,
                    "url": f"https://www.youtube.com/watch?v={video_id}"
                    if video_id
                    else None,
                }
            )

        if results:
            cache.set(
                __name__,
                params,
                {"results": results, "instruction": self.response_directive},
            )

        return {"results": results, "instruction": self.response_directive}
