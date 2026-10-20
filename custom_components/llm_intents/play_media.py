"""Play video tool for Tools for Assist integration."""

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import llm
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)

# Official device_class values that support video
VIDEO_CAPABLE_DEVICE_CLASSES = {"tv", "receiver"}
# Device classes that are explicitly audio-only
AUDIO_ONLY_DEVICE_CLASSES = {"speaker"}


@dataclass
class MediaPlayerInfo:
    """Information about a video-capable media player."""

    entity_id: str
    area_id: str | None


def resolve_area_id(hass: HomeAssistant, area_input: str) -> str | None:
    """
    Resolve an area name or ID to a valid area ID.

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
        if (
            area_input_lower in area.name.lower()
            or area.name.lower() in area_input_lower
        ):
            _LOGGER.debug(
                "Fuzzy matched area '%s' to '%s' (id: %s)",
                area_input,
                area.name,
                area.id,
            )
            return area.id

    return None


def get_video_capable_media_players(
    hass: HomeAssistant,
) -> list[MediaPlayerInfo]:
    """
    Find media players that support video playback.

    Uses device_class to determine video capability:
    - tv, receiver = video capable
    - speaker = audio only
    - no device_class = skipped (must be explicitly configured)

    Args:
        hass: Home Assistant instance

    Returns:
        List of entity_ids for video-capable media players

    """
    entity_registry = er.async_get(hass)

    video_capable_entities = []

    for state in hass.states.async_all():
        if not state.entity_id.startswith("media_player."):
            continue

        if not async_should_expose(hass, "conversation", state.entity_id):
            continue

        # Use device_class to determine video capability
        device_class = state.attributes.get("device_class")
        if not device_class:
            _LOGGER.debug(
                "Entity %s has no device_class set, skipping",
                state.entity_id,
            )
            continue

        features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
        if not (features & MediaPlayerEntityFeature.PLAY_MEDIA):
            _LOGGER.debug(
                "Entity %s does not support MediaPlayerEntityFeature.PLAY_MEDIA, skipping",
                state.entity_id,
            )
            continue

        device_class_lower = device_class.lower()

        if device_class_lower in AUDIO_ONLY_DEVICE_CLASSES:
            _LOGGER.debug(
                "Entity %s has audio-only device_class: %s, skipping",
                state.entity_id,
                device_class,
            )
            continue
        elif device_class_lower not in VIDEO_CAPABLE_DEVICE_CLASSES:
            _LOGGER.debug(
                "Entity %s has unknown device_class: %s, skipping",
                state.entity_id,
                device_class,
            )
            continue

        _LOGGER.debug(
            "Entity %s has video-capable device_class: %s",
            state.entity_id,
            device_class,
        )

        # Lifted from homeassistant/components/homeassistant/llm.py
        # Only do the additional work to retrieve area names if we've passed the basic checks already
        entity_entry = entity_registry.async_get(state.entity_id)

        video_capable_entities.append(
            MediaPlayerInfo(
                entity_id=state.entity_id,
                area_id=entity_entry.area_id if entity_entry else None,
            )
        )

    _LOGGER.debug(
        "Video-capable media players: %s",
        video_capable_entities,
    )

    return video_capable_entities


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

    parameters = vol.Schema({})

    def __init__(self, config: dict, hass: HomeAssistant) -> None:
        """Initialize the play video tool."""
        super().__init__(config, hass)
        self.video_players = sorted(
            get_video_capable_media_players(hass=self.hass),
            key=lambda p: p.entity_id,
        )

        PlayVideoTool.parameters = vol.Schema(
            {
                vol.Required(
                    "video_url",
                    description="The URL of the video to play (e.g., YouTube URL)",
                ): str,
                vol.Optional(
                    "entity_id",
                    description="The entity_id of the media player",
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[player.entity_id for player in self.video_players]
                        if self.video_players
                        else ["no video-capable devices available"],
                        multiple=True,
                    ),
                ),
                vol.Optional(
                    "area",
                    description="The area name or ID to target all media players in that area",
                ): str,
                vol.Optional(
                    "device_id",
                    description="The device_id of the media player device",
                ): str,
            },
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

            if not area_id:
                _LOGGER.warning(
                    "Could not resolve area '%s' to a valid area_id",
                    area_input,
                )
                return {
                    "success": False,
                    "error": f"Could not find area '{area_input}'. Please check the area name and try again.",
                }

            _LOGGER.debug("Resolved area '%s' to area_id '%s'", area_input, area_id)

            video_players = [
                player for player in self.video_players if area_id == player.area_id
            ]

            if not video_players:
                _LOGGER.warning(
                    "No video-capable media players found in area '%s'",
                    area_input,
                )
                return {
                    "success": False,
                    "error": f"No video-capable media players found in area '{area_input}'.",
                }

            player_entity_ids = [player.entity_id for player in video_players]
            if "entity_id" in target:
                existing = target["entity_id"]
                if isinstance(existing, str):
                    target["entity_id"] = [existing, *player_entity_ids]
                else:
                    target["entity_id"] = list(existing) + player_entity_ids
            else:
                target["entity_id"] = player_entity_ids

            _LOGGER.debug("Targeting video-capable players: %s", video_players)

        if device_id:
            target["device_id"] = device_id

        if not target:
            # If there is only a single capable media player, just use it
            video_players = list(self.video_players)

            if not video_players:
                _LOGGER.warning("No video-capable media players found")
                return {
                    "success": False,
                    "error": "No video-capable media players found.",
                }

            if len(video_players) == 1:
                target["entity_id"] = [player.entity_id for player in video_players]
                _LOGGER.debug("Targeting video-capable player: %s", video_players)
            else:
                # No player specified and we dont have exactly 1 player result
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

            _LOGGER.debug(
                "media_player.play_media completed successfully for %s",
                target_desc,
            )

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
