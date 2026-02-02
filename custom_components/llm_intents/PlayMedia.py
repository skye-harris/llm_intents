"""Play video tool for Tools for Assist integration."""

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .BaseTool import BaseTool

_LOGGER = logging.getLogger(__name__)


class PlayVideoTool(BaseTool):
    """Tool for playing video on a media player."""

    name = "play_video"

    description = (
        "Use this tool to play a video URL on a media player device. "
        "Provide the video URL and specify the target using entity_id, area_id, or device_id."
    )

    prompt_description = (
        "Use the `play_video` tool to play video URLs on media players:\n"
        "- Requires a video URL and a target (entity_id, area_id, or device_id).\n"
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
                "area_id",
                description="The area_id to target all media players in that area (e.g., living_room)",
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
        area_id = tool_input.tool_args.get("area_id")
        device_id = tool_input.tool_args.get("device_id")

        # Build target - at least one must be specified
        target = {}

        if entity_id:
            target["entity_id"] = entity_id

        if area_id:
            target["area_id"] = area_id

        if device_id:
            target["device_id"] = device_id

        if not target:
            return {
                "error": "Must specify at least one of: entity_id, area_id, or device_id"
            }

        # Build a description of the target for messages
        target_desc = entity_id or area_id or device_id

        try:
            await hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "media_content_id": video_url,
                    "media_content_type": "video",
                },
                target=target,
                blocking=True,
            )

            return {
                "success": True,
                "message": f"Now playing video on {target_desc}",
                "video_url": video_url,
            }

        except Exception:
            _LOGGER.exception("Failed to play video on %s", target_desc)
            return {"error": f"Failed to play video on {target_desc}"}
