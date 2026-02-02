"""Play video tool for Tools for Assist integration."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .BaseTool import BaseTool

_LOGGER = logging.getLogger(__name__)


def resolve_area_id(hass: HomeAssistant, area_input: str) -> str | None:
    """Resolve an area name or ID to a valid area ID.

    Args:
        hass: Home Assistant instance
        area_input: Area name or ID provided by the user/LLM

    Returns:
        The resolved area_id, or None if not found
    """
    area_registry = ar.async_get(hass)

    area = area_registry.async_get_area(area_input)

    if area:
        return area.id

    area_input_lower = area_input.lower()

    for area in area_registry.async_list_areas():
        if area.name.lower() == area_input_lower:
            return area.id

    for area in area_registry.async_list_areas():
        if area_input_lower in area.name.lower() or area.name.lower() in area_input_lower:
            _LOGGER.debug("Fuzzy matched area '%s' to '%s' (id: %s)", area_input, area.name, area.id)
            return area.id

    return None


class PlayVideoTool(BaseTool):
    """Tool for playing video on a media player."""

    name = "play_video"

    description = (
        "Use this tool to play a video URL on a media player device. "
        "Provide the video URL and specify the target using entity_id, area_id, or device_id."
    )

    prompt_description = (
        "Use the `play_video` tool to play video URLs on media players:\n"
        "- Requires a video URL and a target (entity_id, area name, or device_id).\n"
        "- Use this after searching YouTube to play the video on a device."
    )

    parameters = vol.Schema(
        {
            vol.Required(
                "video_url",
                description="The URL of the video to play (e.g., YouTube URL)",
            ): str,
            vol.Optional(
                "entity_id",
                description="The entity_id of the media player (e.g., media_player.living_room_tv)",
            ): str,
            vol.Optional(
                "area",
                description="The area name or ID to target all media players in that area (e.g., 'Living Room' or 'living_room')",
            ): str,
            vol.Optional(
                "device_id",
                description="The device_id of the media player device",
            ): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool to play video."""
        video_url = tool_input.tool_args["video_url"]
        entity_id = tool_input.tool_args.get("entity_id")
        area_input = tool_input.tool_args.get("area")
        device_id = tool_input.tool_args.get("device_id")

        _LOGGER.debug(
            "play_video called with video_url=%s, entity_id=%s, area=%s, device_id=%s",
            video_url,
            entity_id,
            area_input,
            device_id,
        )

        # Build target - at least one must be specified
        target = {}

        if entity_id:
            target["entity_id"] = entity_id

        if area_input:
            area_id = resolve_area_id(hass, area_input)

            if area_id:
                _LOGGER.debug("Resolved area '%s' to area_id '%s'", area_input, area_id)
                target["area_id"] = area_id
            else:
                _LOGGER.warning("Could not resolve area '%s' to a valid area_id", area_input)
                return {
                    "success": False,
                    "error": f"Could not find area '{area_input}'. Please check the area name.",
                }

        if device_id:
            target["device_id"] = device_id

        if not target:
            _LOGGER.warning("play_video called without any target specified")
            return {
                "success": False,
                "error": "Must specify at least one of: entity_id, area, or device_id",
            }

        # Build a description of the target for messages
        target_desc = entity_id or area_input or device_id
        service_data = {
            "media_content_id": video_url,
            "media_content_type": "url",
        }

        _LOGGER.debug(
            "Calling media_player.play_media with target=%s, service_data=%s",
            target,
            service_data,
        )

        try:
            await hass.services.async_call(
                "media_player",
                "play_media",
                service_data,
                target=target,
                blocking=True,
            )

            _LOGGER.debug("media_player.play_media completed successfully for %s", target_desc)

            return {
                "success": True,
                "message": f"Now playing video on {target_desc}",
                "video_url": video_url,
            }

        except Exception as err:
            _LOGGER.exception("Failed to play video on %s", target_desc)
            return {
                "success": False,
                "error": f"Failed to play video on {target_desc}: {err}",
            }
