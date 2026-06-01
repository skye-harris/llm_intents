"""Scene Presets LLM tools."""

import json
import logging
import random
from pathlib import Path

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType

from .base_tool import BaseTool

_LOGGER = logging.getLogger(__name__)

SCENE_PRESETS_DOMAIN = "scene_presets"


def _load_presets(hass: HomeAssistant) -> dict:
    """Load preset data from scene_presets installation."""
    base = Path(hass.config.config_dir) / "custom_components" / "scene_presets"
    presets_path = base / "presets.json"
    if not presets_path.exists():
        return {}
    try:
        with presets_path.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _LOGGER.warning("Could not load presets.json: %s", e)
        return {}

    custom_path = base / "userdata" / "custom" / "presets.json"
    if custom_path.exists():
        try:
            with custom_path.open() as f:
                custom = json.load(f)
            data.setdefault("presets", []).extend(
                [{**p, "custom": True} for p in custom.get("presets", [])]
            )
            data.setdefault("categories", []).extend(
                [{**c, "custom": True} for c in custom.get("categories", [])]
            )
        except json.JSONDecodeError as e:
            _LOGGER.warning("Could not load custom presets: %s", e)

    return data


def _find_preset_by_name(data: dict, name: str) -> dict | None:
    """Find a preset by case-insensitive name match."""
    name_lower = name.lower().strip()
    for preset in data.get("presets", []):
        if preset.get("name", "").lower() == name_lower:
            return preset
    return None


def _build_targets(entity_ids: list[str], area_ids: list[str]) -> dict[str, list[str]]:
    """Build a scene_presets targets dict from entity and area ID lists."""
    targets: dict[str, list[str]] = {}
    if entity_ids:
        targets["entity_id"] = entity_ids
    if area_ids:
        targets["area_id"] = area_ids
    return targets


def _find_preset_by_mood(data: dict, mood: str) -> dict | None:
    """Return a random preset whose category name matches mood (case-insensitive)."""
    mood_lower = mood.lower().strip()
    categories = {c["id"]: c["name"] for c in data.get("categories", [])}
    matches = [
        p
        for p in data.get("presets", [])
        if categories.get(p.get("categoryId", ""), "").lower() == mood_lower
    ]
    return random.choice(matches) if matches else None  # noqa: S311


def _resolve_area_ids(hass: HomeAssistant, area_ids: list[str]) -> list[str]:
    """Resolve area display names or aliases to HA area ID slugs."""
    if not area_ids:
        return area_ids
    try:
        registry = ar.async_get(hass)
        resolved = []
        for area_id in area_ids:
            if registry.async_get_area(area_id):
                resolved.append(area_id)
                continue
            area = registry.async_get_area_by_name(area_id)
            if area is None:
                matches = registry.async_get_areas_by_alias(area_id)
                area = matches[0] if matches else None
            resolved.append(area.id if area else area_id)
        return resolved
    except AttributeError:
        return area_ids


def _lookup_preset(
    data: dict, mood: str | None, preset_name: str | None
) -> tuple[dict | None, dict | None]:
    """Resolve mood or preset_name to a preset entry, or return an error dict."""
    if mood:
        preset = _find_preset_by_mood(data, mood)
        if not preset:
            categories = sorted({c["name"] for c in data.get("categories", [])})
            return None, {
                "error": f"No mood '{mood}' found.",
                "available_moods": categories,
            }
        return preset, None
    preset = _find_preset_by_name(data, preset_name) or _find_preset_by_mood(
        data, preset_name
    )
    if not preset:
        return None, {
            "error": f"No preset or mood named '{preset_name}' found. Call ListScenePresets to see available options.",
            "available_count": len(data.get("presets", [])),
        }
    return preset, None


def _scene_presets_available(hass: HomeAssistant) -> bool:
    return hass.services.has_service(SCENE_PRESETS_DOMAIN, "apply_preset")


class ListScenePresetsTool(BaseTool):
    """Tool to list available scene presets."""

    name = "ListScenePresets"
    description = (
        "List all available scene presets with their names, IDs, and categories. "
        "Call this first to discover preset names before applying one."
    )
    prompt_description = None
    parameters = vol.Schema({})

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        if not _scene_presets_available(hass):
            return {"error": "scene_presets integration is not installed or loaded"}

        data = _load_presets(hass)
        if not data:
            return {"error": "Could not load scene presets data"}

        categories = {c["id"]: c["name"] for c in data.get("categories", [])}
        moods = sorted(categories.values())
        presets = [
            {
                "name": p["name"],
                "id": p["id"],
                "mood": categories.get(p.get("categoryId", ""), "Defaults"),
                **({"custom": True} if p.get("custom") else {}),
            }
            for p in data.get("presets", [])
        ]
        return {"moods": moods, "presets": presets}


class ApplyScenePresetTool(BaseTool):
    """Tool to apply a scene preset to lights."""

    name = "SetLightingScene"
    description = "Set a lighting scene or mood in a room. Provide mood and area_ids."
    prompt_description = (
        "Use SetLightingScene whenever the user requests a lighting scene, mood, or ambiance. "
        "Provide mood or preset_name along with area_ids or entity_ids. "
        "For requests that only change brightness, use HassLightSet instead. "
        "After applying a scene, tell the user which mood and preset were used "
        "(from the 'mood' and 'preset' fields in the response). "
        "When making an existing scene dynamic, pass the preset name from the previous response "
        "as preset_name rather than using mood, so the same preset is kept."
    )

    @staticmethod
    def update_args(hass: HomeAssistant) -> None:
        """Stamp available moods from presets.json into the tool description."""
        presets_path = (
            Path(hass.config.config_dir)
            / "custom_components"
            / "scene_presets"
            / "presets.json"
        )
        if not presets_path.exists():
            return
        try:
            with presets_path.open() as f:
                data = json.load(f)
            moods = ", ".join(c["name"] for c in data.get("categories", []))
        except (OSError, json.JSONDecodeError):
            return
        ApplyScenePresetTool.description = (
            "Set a lighting scene or mood in a room. Use this tool directly without asking for confirmation. "
            f"Available moods: {moods}. "
            "Use for requests like 'set the bedroom light to party', 'set bedroom lights to cozy', "
            "'make it relaxing', 'scene preset', or any mood or ambiance request. "
            "Provide mood and area_ids (e.g. area_ids=['bedroom'])."
        )

    parameters = vol.Schema(
        {
            vol.Optional(
                "mood",
                description="Mood or ambiance category (e.g. 'Cozy', 'Refreshing', 'Party vibes', 'Serenity'). Use this instead of preset_name when the user describes an atmosphere.",
            ): str,
            vol.Optional(
                "preset_name",
                description="Exact preset name (e.g. 'Relax', 'Arctic aurora'). Use mood instead when the user describes a general atmosphere.",
            ): str,
            vol.Optional(
                "entity_ids",
                description="Light entity IDs to apply the preset to (e.g. ['light.bedroom_lamp'])",
            ): [str],
            vol.Optional(
                "area_ids",
                description="Area IDs to apply the preset to (e.g. ['living_room', 'bedroom'])",
            ): [str],
            vol.Optional(
                "brightness",
                description="Override brightness (0-255). Omit to use preset default.",
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            vol.Optional(
                "dynamic",
                description="Start an endlessly looping dynamic scene instead of a one-shot apply. Default false.",
            ): bool,
            vol.Optional(
                "interval",
                description="Seconds between color changes for a dynamic scene (5-300). Default 60.",
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        if not _scene_presets_available(hass):
            return {"error": "scene_presets integration is not installed or loaded"}

        args = tool_input.tool_args
        mood = args.get("mood")
        preset_name = args.get("preset_name")

        if not mood and not preset_name:
            return {"error": "Provide either mood or preset_name"}

        data = _load_presets(hass)
        preset, err = _lookup_preset(data, mood, preset_name)
        if err:
            return err

        entity_ids = args.get("entity_ids") or []
        area_ids = args.get("area_ids") or []
        if not entity_ids and not area_ids:
            return {"error": "Must specify at least one entity_id or area_id"}

        area_ids = _resolve_area_ids(hass, area_ids)
        targets = _build_targets(entity_ids, area_ids)

        is_dynamic = args.get("dynamic", False)
        service_data: dict = {
            "preset_id": preset["id"],
            "targets": targets,
            "transition": 1,
        }
        if (brightness := args.get("brightness")) is not None:
            service_data["brightness"] = brightness

        if is_dynamic:
            service_data["interval"] = args.get("interval", 60)
            service_name = "start_dynamic_scene"
        else:
            service_name = "apply_preset"

        try:
            await hass.services.async_call(
                SCENE_PRESETS_DOMAIN,
                service_name,
                service_data,
                blocking=True,
            )
        except Exception as e:
            _LOGGER.exception("Error applying scene preset '%s'", preset["name"])
            return {"error": str(e)}

        result = {
            "success": True,
            "preset": preset["name"],
            "dynamic": is_dynamic,
            "targets": targets,
        }
        if mood:
            result["mood"] = mood
        return result


class StopDynamicScenesTool(BaseTool):
    """Tool to stop dynamic scenes on lights."""

    name = "StopDynamicScenes"
    description = (
        "Stop all active dynamic (looping) scenes on the specified lights or areas. "
        "Provide entity_ids and/or area_ids to stop scenes only on those targets, "
        "or call with no arguments to stop all dynamic scenes everywhere."
    )
    prompt_description = None

    parameters = vol.Schema(
        {
            vol.Optional(
                "entity_ids",
                description="Light entity IDs to stop dynamic scenes on",
            ): [str],
            vol.Optional(
                "area_ids",
                description="Area IDs to stop dynamic scenes on",
            ): [str],
            vol.Optional(
                "stop_all",
                description="Set to true to stop all dynamic scenes regardless of target",
            ): bool,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> JsonObjectType:
        """Call the tool."""
        if not _scene_presets_available(hass):
            return {"error": "scene_presets integration is not installed or loaded"}

        args = tool_input.tool_args
        stop_all = args.get("stop_all", False)
        entity_ids = args.get("entity_ids") or []
        area_ids = args.get("area_ids") or []

        if stop_all or (not entity_ids and not area_ids):
            await hass.services.async_call(
                SCENE_PRESETS_DOMAIN,
                "stop_all_dynamic_scenes",
                {},
                blocking=True,
            )
            return {"success": True, "stopped": "all"}

        targets = _build_targets(entity_ids, area_ids)

        try:
            await hass.services.async_call(
                SCENE_PRESETS_DOMAIN,
                "stop_dynamic_scenes_for_targets",
                {"targets": targets},
                blocking=True,
            )
        except Exception as e:
            _LOGGER.exception("Error stopping dynamic scenes")
            return {"error": str(e)}

        return {"success": True, "stopped_for": targets}
