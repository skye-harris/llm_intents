"""Wikipedia tool using wikipedia-api library."""

import logging

import nanoe5
import numpy as np
import voluptuous as vol
import wikipediaapi
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType
from wikipediaapi import WikipediaException

from .base_tool import BaseTool
from .cache import SQLiteCache
from .const import CONF_WIKIPEDIA_NUM_RESULTS

_LOGGER = logging.getLogger(__name__)


def _flatten_sections(sections: list) -> list[dict]:
    """Recursively flatten sections into a flat list of title+text dicts."""
    result: list[dict] = []
    for section in sections:
        result.append({"title": section.title, "text": section.text})
        result.extend(_flatten_sections(section.sections))
    return result


def _find_best_section(
    query: str,
    sections: list[dict],
) -> str | None:
    """Return the section text most similar to the query using embeddings."""
    if not sections:
        return None

    try:
        query_emb = nanoe5.query(query)
        section_texts = [s["text"] for s in sections if s["text"]]
        if not section_texts:
            _LOGGER.debug("no section texts found")
            return None
        section_embs = nanoe5.passage(section_texts)
        scores = section_embs @ query_emb
        best_idx = int(np.argmax(scores))
        _LOGGER.debug("Best score = %s", scores[best_idx])
        return section_texts[best_idx]
    except Exception:
        _LOGGER.debug(
            "Embedding search failed, falling back to first section", exc_info=True
        )
        return sections[0]["text"] if sections else None


class SearchWikipediaTool(BaseTool):
    """Tool for searching Wikipedia."""

    name = "search_wikipedia"
    description = "Use this tool to retrieve information from Wikipedia on a specified subject matter"
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Required(
                "query",
                description="The subject matter to search Wikipedia for",
            ): str,
        },
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        config_data = self.config
        query = tool_input.tool_args["query"]
        num_results = int(config_data.get(CONF_WIKIPEDIA_NUM_RESULTS, 1))

        _LOGGER.info("Wikipedia search requested for: %s", query)

        try:
            cache = SQLiteCache()
            cache_key = {"query": query, "num_results": num_results}
            cached_response = cache.get(__name__, cache_key)
            if cached_response:
                return cached_response

            wiki = wikipediaapi.AsyncWikipedia(
                user_agent="ToolsForAssist/0.0 (https://github.com/skye-harris/llm_intents, HomeAssistant integration)",
                language="en",
                max_retries=1,
                retry_wait=1,
            )

            search_results = await wiki.search(query, limit=num_results)

            if not search_results.pages:
                return {"result": f"No Wikipedia articles found for '{query}'"}

            results = []
            for title, page in search_results.pages.items():
                sections_raw = await page.sections

                sections = _flatten_sections(sections_raw)
                best_section = _find_best_section(query, sections)

                result: dict = {
                    "title": title,
                    "url": await page.fullurl,
                }

                if best_section is not None:
                    result["section"] = best_section

                results.append(result)

            response = {"results": results}
            cache.set(__name__, cache_key, response)
            return response

        except WikipediaException as e:
            _LOGGER.exception("Wikipedia API error")
            return {"error": f"Wikipedia API error: {e!s}"}
        except Exception as e:
            _LOGGER.exception("Wikipedia search encountered an error")
            return {"error": f"Error searching Wikipedia: {e!s}"}
