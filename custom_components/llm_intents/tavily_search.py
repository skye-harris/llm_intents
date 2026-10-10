"""Tavily web search tool."""

import logging
from http import HTTPStatus
from typing import Any

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .base_web_search import SearchWebTool
from .const import (
    CONF_PROVIDER_API_KEYS,
    CONF_TAVILY_CHUNKS_EXCLUDED_DEPTHS,
    CONF_TAVILY_CHUNKS_PER_SOURCE,
    CONF_TAVILY_COUNTRY,
    CONF_TAVILY_COUNTRY_EXCLUDED_DEPTHS,
    CONF_TAVILY_INCLUDE_ANSWER,
    CONF_TAVILY_INCLUDE_RAW_CONTENT,
    CONF_TAVILY_NUM_RESULTS,
    CONF_TAVILY_SEARCH_DEPTH,
    PROVIDER_TAVILY,
)

_LOGGER = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

TAVILY_TOPICS = ["general", "news", "finance"]
TAVILY_TIME_RANGES = ["day", "week", "month", "year"]


class TavilySearchTool(SearchWebTool):
    """Tool for searching the web via the Tavily Search API."""

    parameters = vol.Schema(
        {
            vol.Required("query", description="The query to search for"): str,
            vol.Optional(
                "topic",
                description=(
                    "Optional content type. Use 'news' for current news and "
                    "'finance' for financial sources. Omit for a general search."
                ),
            ): vol.In(TAVILY_TOPICS),
            vol.Optional(
                "time_range",
                description=(
                    "Optional recency filter: 'day', 'week', 'month' or 'year'. "
                    "Omit to search without a date filter."
                ),
            ): vol.In(TAVILY_TIME_RANGES),
        },
    )

    async def async_search(
        self,
        query: str,
        **kwargs: Any,
    ) -> list:
        """Call the tool."""
        provider_keys = self.config.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_TAVILY, "")
        num_results = int(self.config.get(CONF_TAVILY_NUM_RESULTS, 2))
        chunks_per_source = int(self.config.get(CONF_TAVILY_CHUNKS_PER_SOURCE, 1))
        search_depth = self.config.get(CONF_TAVILY_SEARCH_DEPTH) or "basic"
        include_answer = bool(self.config.get(CONF_TAVILY_INCLUDE_ANSWER, False))
        include_raw_content = bool(
            self.config.get(CONF_TAVILY_INCLUDE_RAW_CONTENT, False)
        )
        country = (self.config.get(CONF_TAVILY_COUNTRY) or "").strip().lower()

        if not api_key:
            error_msg = "Tavily API key not configured"
            raise RuntimeError(error_msg)

        session = async_get_clientsession(self.hass)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        payload = {
            "query": query,
            "max_results": num_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
        }

        topic = kwargs.get("topic") or "general"

        # Only send the settings that apply to this search. Tavily applies the
        # country boost to general searches only and rejects it on the fast and
        # ultra-fast depths, and it returns a single summary per result on
        # ultra-fast, where chunks_per_source has no effect.
        country_applies = (
            topic == "general"
            and search_depth not in CONF_TAVILY_COUNTRY_EXCLUDED_DEPTHS
        )
        chunks_apply = search_depth not in CONF_TAVILY_CHUNKS_EXCLUDED_DEPTHS

        if country and not country_applies:
            _LOGGER.debug(
                "Tavily country boost (%s) not sent for topic=%s search_depth=%s",
                country,
                topic,
                search_depth,
            )
        elif country:
            payload["country"] = country

        if not chunks_apply:
            _LOGGER.debug(
                "Tavily chunks_per_source not sent for search_depth=%s",
                search_depth,
            )
        else:
            payload["chunks_per_source"] = chunks_per_source

        for key in ("topic", "time_range"):
            if kwargs.get(key):
                payload[key] = kwargs[key]

        async with session.post(
            TAVILY_SEARCH_URL,
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status != HTTPStatus.OK:
                # Read the body as text: an error from an intermediary is not
                # necessarily JSON, and a whole error page must not be handed
                # to the model as the tool's error message.
                body = await resp.text()
                error_msg = (
                    f"Web search received a HTTP {resp.status} error from Tavily: "
                    f"{body[:500]}"
                )
                raise RuntimeError(error_msg)

            response_content = await resp.json()
            results = []

            answer = response_content.get("answer")
            if include_answer and answer:
                results.append(
                    {
                        "title": "Tavily answer",
                        "content": await self.cleanup_text(str(answer)),
                    }
                )

            for result in response_content.get("results", []):
                title = result.get("title", "")
                content = result.get("content") or ""
                if include_raw_content:
                    content = result.get("raw_content") or content

                content = await self.cleanup_text(content)
                results.append({"title": title, "content": content})

            return results
