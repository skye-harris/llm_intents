"""Tests for the scene_presets LLM tools."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.llm_intents.scene_presets_tools import (
    ApplyScenePresetTool,
    ListScenePresetsTool,
    StopDynamicScenesTool,
    _find_preset_by_name,
    _load_presets,
    _resolve_area_ids,
)

SAMPLE_PRESETS_JSON = """{
    "categories": [
        {"id": "cat-defaults", "name": "Defaults"},
        {"id": "cat-cozy", "name": "Cozy"}
    ],
    "presets": [
        {"id": "uuid-relax", "name": "Relax", "categoryId": "cat-defaults", "bri": 200, "lights": []},
        {"id": "uuid-energize", "name": "Energize", "categoryId": "cat-defaults", "bri": 255, "lights": []},
        {"id": "uuid-cozy", "name": "Cozy Glow", "categoryId": "cat-cozy", "bri": 150, "lights": []}
    ]
}"""

SAMPLE_CUSTOM_PRESETS_JSON = """{
    "categories": [],
    "presets": [
        {"id": "uuid-custom", "name": "My Custom Scene", "categoryId": "", "bri": 180, "lights": []}
    ]
}"""

SAMPLE_PRESET_DATA = {
    "categories": [
        {"id": "cat-defaults", "name": "Defaults"},
        {"id": "cat-cozy", "name": "Cozy"},
    ],
    "presets": [
        {"id": "uuid-relax", "name": "Relax", "categoryId": "cat-defaults"},
        {"id": "uuid-energize", "name": "Energize", "categoryId": "cat-defaults"},
        {"id": "uuid-cozy", "name": "Cozy Glow", "categoryId": "cat-cozy"},
    ],
}


@pytest.fixture
def mock_hass_with_scene_presets(mock_hass: HomeAssistant) -> HomeAssistant:
    """Mock hass with scene_presets services available."""
    mock_hass.services = MagicMock()
    mock_hass.services.has_service.return_value = True
    mock_hass.services.async_call = AsyncMock()
    mock_hass.config = MagicMock()
    mock_hass.config.config_dir = "/config"
    return mock_hass


@pytest.fixture
def mock_hass_no_scene_presets(mock_hass: HomeAssistant) -> HomeAssistant:
    """Mock hass without scene_presets services available."""
    mock_hass.services = MagicMock()
    mock_hass.services.has_service.return_value = False
    mock_hass.config = MagicMock()
    mock_hass.config.config_dir = "/config"
    return mock_hass


@pytest.fixture
def llm_context() -> llm.LLMContext:
    """Return a dummy LLM context."""
    return llm.LLMContext(
        platform="test", context=None, language="en", assistant=None, device_id=None
    )


# =============================================================================
# _find_preset_by_name() tests
# =============================================================================


def test_find_preset_by_name_exact_match() -> None:
    """Exact name match returns the correct preset."""
    assert _find_preset_by_name(SAMPLE_PRESET_DATA, "Relax")["id"] == "uuid-relax"


def test_find_preset_by_name_case_insensitive() -> None:
    """Name lookup is case-insensitive."""
    assert _find_preset_by_name(SAMPLE_PRESET_DATA, "relax")["id"] == "uuid-relax"
    assert _find_preset_by_name(SAMPLE_PRESET_DATA, "RELAX")["id"] == "uuid-relax"
    assert _find_preset_by_name(SAMPLE_PRESET_DATA, "cozy glow")["id"] == "uuid-cozy"


def test_find_preset_by_name_not_found() -> None:
    """Returns None when no preset matches the name."""
    assert _find_preset_by_name(SAMPLE_PRESET_DATA, "Nonexistent") is None


def test_find_preset_by_name_empty_data() -> None:
    """Returns None when preset data is empty."""
    assert _find_preset_by_name({}, "Relax") is None


# =============================================================================
# _load_presets() tests
# =============================================================================


def test_load_presets_missing_file() -> None:
    """Returns empty dict when presets.json does not exist."""
    hass = MagicMock()
    hass.config.config_dir = "/config"
    with patch("pathlib.Path.exists", return_value=False):
        result = _load_presets(hass)
    assert result == {}


def test_load_presets_base_only() -> None:
    """Loads presets.json when no custom file exists."""
    hass = MagicMock()
    hass.config.config_dir = "/config"

    _call = [0]

    def exists_side_effect() -> bool:
        _call[0] += 1
        return _call[0] == 1  # True for presets_path, False for custom_path

    with (
        patch("pathlib.Path.exists", side_effect=exists_side_effect),
        patch("pathlib.Path.open", mock_open(read_data=SAMPLE_PRESETS_JSON)),
    ):
        result = _load_presets(hass)

    assert len(result["presets"]) == 3
    assert result["presets"][0]["name"] == "Relax"


def test_load_presets_merges_custom() -> None:
    """Custom presets are appended and flagged."""
    hass = MagicMock()
    hass.config.config_dir = "/config"

    call_count = [0]

    def open_side_effect(*args: Any, **kwargs: Any) -> Any:
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_open(read_data=SAMPLE_PRESETS_JSON)()
        return mock_open(read_data=SAMPLE_CUSTOM_PRESETS_JSON)()

    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.open", side_effect=open_side_effect),
    ):
        result = _load_presets(hass)

    names = [p["name"] for p in result["presets"]]
    assert "Relax" in names
    assert "My Custom Scene" in names
    custom = next(p for p in result["presets"] if p["name"] == "My Custom Scene")
    assert custom.get("custom") is True


# =============================================================================
# _resolve_area_ids() tests
# =============================================================================


def _make_area_registry(
    areas_by_id: dict, areas_by_name: dict, areas_by_alias: dict | None = None
) -> MagicMock:
    """Build a minimal area registry mock."""
    reg = MagicMock()
    reg.async_get_area.side_effect = areas_by_id.get
    reg.async_get_area_by_name.side_effect = areas_by_name.get
    reg.async_get_areas_by_alias.side_effect = lambda alias: (areas_by_alias or {}).get(
        alias, []
    )
    return reg


def test_resolve_area_ids_slug_passthrough() -> None:
    """Already-valid slugs are returned unchanged."""
    hass = MagicMock()
    area = MagicMock()
    area.id = "bedroom"
    reg = _make_area_registry({"bedroom": area}, {})
    with patch(
        "custom_components.llm_intents.scene_presets_tools.ar.async_get",
        return_value=reg,
    ):
        result = _resolve_area_ids(hass, ["bedroom"])
    assert result == ["bedroom"]


def test_resolve_area_ids_name_to_slug() -> None:
    """Display name 'Bedroom' is resolved to slug 'bedroom'."""
    hass = MagicMock()
    area = MagicMock()
    area.id = "bedroom"
    reg = _make_area_registry({}, {"Bedroom": area})
    with patch(
        "custom_components.llm_intents.scene_presets_tools.ar.async_get",
        return_value=reg,
    ):
        result = _resolve_area_ids(hass, ["Bedroom"])
    assert result == ["bedroom"]


def test_resolve_area_ids_unknown_passthrough() -> None:
    """Unknown area IDs are passed through unchanged."""
    hass = MagicMock()
    reg = _make_area_registry({}, {})
    with patch(
        "custom_components.llm_intents.scene_presets_tools.ar.async_get",
        return_value=reg,
    ):
        result = _resolve_area_ids(hass, ["nonexistent"])
    assert result == ["nonexistent"]


def test_resolve_area_ids_by_alias() -> None:
    """Area aliases are resolved to the area slug."""
    hass = MagicMock()
    area = MagicMock()
    area.id = "living_room"
    reg = _make_area_registry({}, {})
    reg.async_get_areas_by_alias = MagicMock(return_value=[area])
    with patch(
        "custom_components.llm_intents.scene_presets_tools.ar.async_get",
        return_value=reg,
    ):
        result = _resolve_area_ids(hass, ["Lounge"])
    assert result == ["living_room"]


def test_resolve_area_ids_empty() -> None:
    """Empty input returns immediately without touching the registry."""
    hass = MagicMock()
    with patch(
        "custom_components.llm_intents.scene_presets_tools.ar.async_get"
    ) as mock_ar:
        result = _resolve_area_ids(hass, [])
    mock_ar.assert_not_called()
    assert result == []


# =============================================================================
# ListScenePresetsTool tests
# =============================================================================


@pytest.fixture
def list_tool(mock_hass_with_scene_presets: HomeAssistant) -> ListScenePresetsTool:
    """Return a ListScenePresetsTool bound to a mock hass."""
    return ListScenePresetsTool({}, mock_hass_with_scene_presets)


@pytest.mark.asyncio
async def test_list_presets_unavailable(
    mock_hass_no_scene_presets: HomeAssistant, llm_context: llm.LLMContext
) -> None:
    """Returns an error when scene_presets is not installed."""
    tool = ListScenePresetsTool({}, mock_hass_no_scene_presets)
    result = await tool.async_call(
        mock_hass_no_scene_presets,
        llm.ToolInput(tool_name="ListScenePresets", tool_args={}),
        llm_context,
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_list_presets_missing_json(
    mock_hass_with_scene_presets: HomeAssistant, llm_context: llm.LLMContext
) -> None:
    """Returns an error when presets.json cannot be found."""
    tool = ListScenePresetsTool({}, mock_hass_with_scene_presets)
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value={},
    ):
        result = await tool.async_call(
            mock_hass_with_scene_presets,
            llm.ToolInput(tool_name="ListScenePresets", tool_args={}),
            llm_context,
        )
    assert "error" in result


@pytest.mark.asyncio
async def test_list_presets_returns_all(
    mock_hass_with_scene_presets: HomeAssistant, llm_context: llm.LLMContext
) -> None:
    """Returns all presets with name, id, and category."""
    tool = ListScenePresetsTool({}, mock_hass_with_scene_presets)
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await tool.async_call(
            mock_hass_with_scene_presets,
            llm.ToolInput(tool_name="ListScenePresets", tool_args={}),
            llm_context,
        )

    assert "moods" in result
    assert result["moods"] == ["Cozy", "Defaults"]
    assert "presets" in result
    presets = result["presets"]
    assert len(presets) == 3
    relax = next(p for p in presets if p["name"] == "Relax")
    assert relax["id"] == "uuid-relax"
    assert relax["mood"] == "Defaults"
    cozy = next(p for p in presets if p["name"] == "Cozy Glow")
    assert cozy["mood"] == "Cozy"


# =============================================================================
# ApplyScenePresetTool tests
# =============================================================================


@pytest.fixture
def apply_tool(mock_hass_with_scene_presets: HomeAssistant) -> ApplyScenePresetTool:
    """Return an ApplyScenePresetTool bound to a mock hass."""
    return ApplyScenePresetTool({}, mock_hass_with_scene_presets)


def _apply_input(**kwargs: Any) -> llm.ToolInput:
    return llm.ToolInput(tool_name="SetLightingScene", tool_args=kwargs)


@pytest.mark.asyncio
async def test_apply_preset_unavailable(
    mock_hass_no_scene_presets: HomeAssistant, llm_context: llm.LLMContext
) -> None:
    """Returns an error when scene_presets is not installed."""
    tool = ApplyScenePresetTool({}, mock_hass_no_scene_presets)
    result = await tool.async_call(
        mock_hass_no_scene_presets,
        _apply_input(preset_name="Relax", entity_ids=["light.x"]),
        llm_context,
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_apply_preset_not_found(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Returns an error when the requested preset does not exist."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(preset_name="Does Not Exist", entity_ids=["light.x"]),
            llm_context,
        )
    assert "error" in result
    assert "Does Not Exist" in result["error"]


@pytest.mark.asyncio
async def test_apply_preset_no_targets(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Returns an error when neither entity_ids nor area_ids are provided."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(preset_name="Relax"),
            llm_context,
        )
    assert "error" in result


@pytest.mark.asyncio
async def test_apply_preset_entity_ids(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Calls apply_preset service with entity targets."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(preset_name="Relax", entity_ids=["light.bedroom"]),
            llm_context,
        )

    assert result["success"] is True
    assert result["preset"] == "Relax"
    assert result["dynamic"] is False
    mock_hass_with_scene_presets.services.async_call.assert_called_once_with(
        "scene_presets",
        "apply_preset",
        {
            "preset_id": "uuid-relax",
            "targets": {"entity_id": ["light.bedroom"]},
            "transition": 1,
        },
        blocking=True,
    )


@pytest.mark.asyncio
async def test_apply_preset_area_ids(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Calls apply_preset service with area targets."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(preset_name="Energize", area_ids=["living_room"]),
            llm_context,
        )

    assert result["success"] is True
    call_args = mock_hass_with_scene_presets.services.async_call.call_args
    assert call_args[0][2]["targets"] == {"area_id": ["living_room"]}
    assert call_args[0][2]["preset_id"] == "uuid-energize"


@pytest.mark.asyncio
async def test_apply_preset_mixed_targets(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Calls apply_preset with both entity_ids and area_ids."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(
                preset_name="Relax",
                entity_ids=["light.lamp"],
                area_ids=["bedroom"],
            ),
            llm_context,
        )

    targets = mock_hass_with_scene_presets.services.async_call.call_args[0][2][
        "targets"
    ]
    assert targets == {"entity_id": ["light.lamp"], "area_id": ["bedroom"]}


@pytest.mark.asyncio
async def test_apply_preset_optional_params(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Brightness is forwarded correctly."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(
                preset_name="Relax",
                entity_ids=["light.x"],
                brightness=128,
            ),
            llm_context,
        )

    data = mock_hass_with_scene_presets.services.async_call.call_args[0][2]
    assert data["brightness"] == 128
    assert data["transition"] == 1
    assert "shuffle" not in data


@pytest.mark.asyncio
async def test_apply_preset_dynamic(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """dynamic=True calls start_dynamic_scene with interval."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(
                preset_name="Cozy Glow",
                entity_ids=["light.living_room"],
                dynamic=True,
                interval=30,
            ),
            llm_context,
        )

    assert result["dynamic"] is True
    call_args = mock_hass_with_scene_presets.services.async_call.call_args[0]
    assert call_args[1] == "start_dynamic_scene"
    assert call_args[2]["interval"] == 30
    assert "shuffle" not in call_args[2]


@pytest.mark.asyncio
async def test_apply_preset_dynamic_default_interval(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """dynamic=True defaults to 60s interval when not specified."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(preset_name="Relax", entity_ids=["light.x"], dynamic=True),
            llm_context,
        )

    data = mock_hass_with_scene_presets.services.async_call.call_args[0][2]
    assert data["interval"] == 60


@pytest.mark.asyncio
async def test_apply_preset_service_error(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Service call failures are caught and returned as an error dict."""
    mock_hass_with_scene_presets.services.async_call = AsyncMock(
        side_effect=Exception("zigbee timeout")
    )
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(preset_name="Relax", entity_ids=["light.x"]),
            llm_context,
        )

    assert "error" in result
    assert "zigbee timeout" in result["error"]


@pytest.mark.asyncio
async def test_apply_preset_no_name_or_mood(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Neither preset_name nor mood → error."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(area_ids=["bedroom"]),
            llm_context,
        )
    assert "error" in result


@pytest.mark.asyncio
async def test_apply_preset_by_mood(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Mood parameter resolves to a random preset in the matching category."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(mood="Cozy", area_ids=["bedroom"]),
            llm_context,
        )

    assert result["success"] is True
    assert result["preset"] == "Cozy Glow"
    call_args = mock_hass_with_scene_presets.services.async_call.call_args[0]
    assert call_args[2]["preset_id"] == "uuid-cozy"
    assert call_args[2]["targets"] == {"area_id": ["bedroom"]}


@pytest.mark.asyncio
async def test_apply_preset_by_mood_case_insensitive(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Mood lookup is case-insensitive."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(mood="cozy", area_ids=["bedroom"]),
            llm_context,
        )
    assert result["success"] is True
    assert result["preset"] == "Cozy Glow"


@pytest.mark.asyncio
async def test_apply_preset_mood_not_found(
    apply_tool: ApplyScenePresetTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Unknown mood returns error with available moods list."""
    with patch(
        "custom_components.llm_intents.scene_presets_tools._load_presets",
        return_value=SAMPLE_PRESET_DATA,
    ):
        result = await apply_tool.async_call(
            mock_hass_with_scene_presets,
            _apply_input(mood="Psychedelic", area_ids=["bedroom"]),
            llm_context,
        )
    assert "error" in result
    assert "available_moods" in result
    assert "Cozy" in result["available_moods"]


# =============================================================================
# StopDynamicScenesTool tests
# =============================================================================


@pytest.fixture
def stop_tool(mock_hass_with_scene_presets: HomeAssistant) -> StopDynamicScenesTool:
    """Return a StopDynamicScenesTool bound to a mock hass."""
    return StopDynamicScenesTool({}, mock_hass_with_scene_presets)


def _stop_input(**kwargs: Any) -> llm.ToolInput:
    return llm.ToolInput(tool_name="StopDynamicScenes", tool_args=kwargs)


@pytest.mark.asyncio
async def test_stop_unavailable(
    mock_hass_no_scene_presets: HomeAssistant, llm_context: llm.LLMContext
) -> None:
    """Returns an error when scene_presets is not installed."""
    tool = StopDynamicScenesTool({}, mock_hass_no_scene_presets)
    result = await tool.async_call(
        mock_hass_no_scene_presets, _stop_input(), llm_context
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_stop_all_when_no_args(
    stop_tool: StopDynamicScenesTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """No arguments → stop_all_dynamic_scenes."""
    result = await stop_tool.async_call(
        mock_hass_with_scene_presets, _stop_input(), llm_context
    )
    assert result["stopped"] == "all"
    mock_hass_with_scene_presets.services.async_call.assert_called_once_with(
        "scene_presets", "stop_all_dynamic_scenes", {}, blocking=True
    )


@pytest.mark.asyncio
async def test_stop_all_explicit(
    stop_tool: StopDynamicScenesTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """stop_all=True → stop_all_dynamic_scenes regardless of targets."""
    result = await stop_tool.async_call(
        mock_hass_with_scene_presets,
        _stop_input(stop_all=True, entity_ids=["light.x"]),
        llm_context,
    )
    assert result["stopped"] == "all"
    call_args = mock_hass_with_scene_presets.services.async_call.call_args[0]
    assert call_args[1] == "stop_all_dynamic_scenes"


@pytest.mark.asyncio
async def test_stop_for_entity_ids(
    stop_tool: StopDynamicScenesTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Stops dynamic scenes for specific entity IDs."""
    result = await stop_tool.async_call(
        mock_hass_with_scene_presets,
        _stop_input(entity_ids=["light.bedroom", "light.lamp"]),
        llm_context,
    )
    assert result["success"] is True
    call_args = mock_hass_with_scene_presets.services.async_call.call_args[0]
    assert call_args[1] == "stop_dynamic_scenes_for_targets"
    assert call_args[2]["targets"] == {"entity_id": ["light.bedroom", "light.lamp"]}


@pytest.mark.asyncio
async def test_stop_for_area_ids(
    stop_tool: StopDynamicScenesTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Stops dynamic scenes for specific area IDs."""
    await stop_tool.async_call(
        mock_hass_with_scene_presets,
        _stop_input(area_ids=["living_room"]),
        llm_context,
    )
    call_args = mock_hass_with_scene_presets.services.async_call.call_args[0]
    assert call_args[1] == "stop_dynamic_scenes_for_targets"
    assert call_args[2]["targets"] == {"area_id": ["living_room"]}


@pytest.mark.asyncio
async def test_stop_service_error(
    stop_tool: StopDynamicScenesTool,
    mock_hass_with_scene_presets: HomeAssistant,
    llm_context: llm.LLMContext,
) -> None:
    """Service call failures are caught and returned as an error dict."""
    mock_hass_with_scene_presets.services.async_call = AsyncMock(
        side_effect=Exception("service failed")
    )
    result = await stop_tool.async_call(
        mock_hass_with_scene_presets,
        _stop_input(entity_ids=["light.x"]),
        llm_context,
    )
    assert "error" in result
