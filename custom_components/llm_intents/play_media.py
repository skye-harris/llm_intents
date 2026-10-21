"""Play video tool for Tools for Assist integration."""

import logging
from dataclasses import dataclass

import voluptuous as vol
from homeassistant.components.homeassistant.llm import async_get_exposed_entities
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
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
    assistant: str,
) -> list[MediaPlayerInfo]:
    """
    Find exposed media players that support video playback.

    Uses device_class to determine video capability:
    - tv, receiver = video capable
    - speaker = audio only
    - no device_class = skipped (must be explicitly configured)

    Args:
        hass: Home Assistant instance
        assistant: Assistant whose exposure settings should be applied

    Returns:
        List of exposed video-capable media players

    """
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    exposed_entities = async_get_exposed_entities(hass, assistant, include_state=False)

    video_capable_entities = []

    for state in hass.states.async_all():
        if state.entity_id not in exposed_entities:
            continue

        if not state.entity_id.startswith("media_player."):
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
        if device_class_lower not in VIDEO_CAPABLE_DEVICE_CLASSES:
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

        area_id = entity_entry.area_id if entity_entry else None
        if area_id is None and entity_entry and entity_entry.device_id:
            device_entry = device_registry.async_get(entity_entry.device_id)
            if device_entry:
                area_id = dr.async_get_effective_area_id(hass, device_entry)

        video_capable_entities.append(
            MediaPlayerInfo(
                entity_id=state.entity_id,
                area_id=area_id,
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
        "Provide the video URL and specify the target using entity_id or area."
    )

    prompt_description = (
        "Use the `play_video` tool to play video URLs on media players:\n"
        "- Requires a video URL and a target (entity_id or area name).\n"
        "- Use this after searching YouTube to play the video on a device."
    )

    parameters = vol.Schema({})

    def __init__(
        self,
        config: dict,
        hass: HomeAssistant,
        llm_context: llm.LLMContext | None = None,
    ) -> None:
        """Initialize the play video tool."""
        super().__init__(config, hass, llm_context)
        self.assistant = (
            llm_context.assistant
            if llm_context and llm_context.assistant
            else "conversation"
        )
        self.video_players = sorted(
            get_video_capable_media_players(
                hass=self.hass,
                assistant=self.assistant,
            ),
            key=lambda player: player.entity_id,
        )

        self.parameters = vol.Schema(
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
        entity_ids = tool_input.tool_args.get("entity_id")
        area_input = tool_input.tool_args.get("area")

        if isinstance(entity_ids, str):
            requested_entity_ids = [entity_ids]
        elif entity_ids:
            requested_entity_ids = list(entity_ids)
        else:
            requested_entity_ids = []

        _LOGGER.debug(
            "play_video called with video_url=%s, entity_id=%s, area=%s",
            video_url,
            entity_ids,
            area_input,
        )

        allowed_entity_ids = {player.entity_id for player in self.video_players}
        invalid_entity_ids = [
            entity_id
            for entity_id in requested_entity_ids
            if entity_id not in allowed_entity_ids
        ]

        if invalid_entity_ids:
            _LOGGER.warning(
                "Requested media players are not exposed to this assistant: %s",
                invalid_entity_ids,
            )
            return {
                "success": False,
                "error": (
                    "Media player(s) not exposed to this assistant: "
                    f"{', '.join(invalid_entity_ids)}"
                ),
            }

        target_entity_ids = list(dict.fromkeys(requested_entity_ids))

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
                    "No exposed video-capable media players found in area '%s'",
                    area_input,
                )
                return {
                    "success": False,
                    "error": f"No video-capable media players found in area '{area_input}'.",
                }

            target_entity_ids = list(
                dict.fromkeys(
                    [
                        *target_entity_ids,
                        *(player.entity_id for player in video_players),
                    ]
                )
            )

            _LOGGER.debug("Targeting video-capable players: %s", video_players)

        if not target_entity_ids:
            # If there is only a single capable media player, just use it
            if len(self.video_players) == 1:
                target_entity_ids = [self.video_players[0].entity_id]
                _LOGGER.debug("Targeting video-capable player: %s", self.video_players)
            else:
                if self.video_players:
                    _LOGGER.warning("play_video called without any target specified")
                    error = "Must specify at least one of: entity_id or area"
                else:
                    _LOGGER.warning("No exposed video-capable media players found")
                    error = "No video-capable media players exposed to this assistant."

                return {"success": False, "error": error}

        target = {"entity_id": target_entity_ids}

        # Build a description of the target for messages
        target_desc = area_input or ", ".join(target_entity_ids)
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
