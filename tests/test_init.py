"""Test the LLM Intents integration."""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.llm_intents import (
    DOMAIN,
    async_migrate_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.llm_intents.const import (
    CONF_BRAVE_ENABLED,
    CONF_GOOGLE_PLACES_API_KEY,
    CONF_GOOGLE_PLACES_ENABLED,
    CONF_GOOGLE_PLACES_LATITUDE,
    CONF_GOOGLE_PLACES_LONGITUDE,
    CONF_GOOGLE_PLACES_NUM_RESULTS,
    CONF_GOOGLE_PLACES_RADIUS,
    CONF_GOOGLE_PLACES_RANKING,
    CONF_GOOGLE_ROUTES_ENABLED,
    CONF_PLACES_PROVIDER,
    CONF_PLACES_PROVIDER_GOOGLE,
    CONF_PLACES_PROVIDER_OPENSTREETMAP,
    CONF_PROVIDER_API_KEYS,
    CONF_SEARCH_PROVIDER,
    CONF_SEARCH_PROVIDER_BRAVE,
    PROVIDER_GOOGLE,
)


class TestLlmIntentsIntegration:
    """Test the LLM Intents integration setup and teardown."""

    @pytest.fixture
    def config_entry(self) -> ConfigEntry:
        """Create a mock config entry."""
        return MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry_id",
            data={
                "use_brave": True,
                "brave_api_key": "test_key",
                "use_wikipedia": True,
            },
            options={},
        )

    async def test_async_setup(self, hass: HomeAssistant) -> None:
        """Test the async_setup function."""
        result = await async_setup(hass, {})

        assert result is True
        assert DOMAIN in hass.data

    async def test_async_setup_entry(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test setting up a config entry."""
        config_entry.add_to_hass(hass)

        with patch("custom_components.llm_intents.setup_llm_functions") as mock_setup:
            result = await async_setup_entry(hass, config_entry)

            assert result is True
            mock_setup.assert_called_once_with(hass, config_entry)

    async def test_async_unload_entry(
        self, hass: HomeAssistant, config_entry: ConfigEntry
    ) -> None:
        """Test unloading a config entry."""
        # Set up runtime_data as it would be after setup
        config_entry.runtime_data = {
            "config": config_entry.data,
            "api": Mock(),
            "unregister_api": [],
        }
        config_entry.add_to_hass(hass)

        with patch(
            "custom_components.llm_intents.cleanup_llm_functions"
        ) as mock_cleanup:
            result = await async_unload_entry(hass, config_entry)

            assert result is True
            mock_cleanup.assert_called_once_with(config_entry)

    async def test_async_migrate_entry_v2_to_v3_migrates_places_key(
        self, hass: HomeAssistant
    ) -> None:
        """
        Test migrating from version 2 migrates google_places_api_key to provider_api_keys.

        The migration now continues to version 4 (places provider), so the
        final update lands on version 4 with the key migration intact.
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=2,
            data={
                CONF_GOOGLE_PLACES_API_KEY: "test_google_api_key",
                "other_config": "value",
            },
            options={},
        )

        # Track what gets updated
        updated_data = {}
        updated_options = {}
        updated_version = None

        def mock_update_entry(entry_obj: ConfigEntry, **kwargs: Any) -> None:
            nonlocal updated_data, updated_options, updated_version
            updated_data = kwargs.get("data", {})
            updated_options = kwargs.get("options", {})
            updated_version = kwargs.get("version")

        hass.config_entries.async_update_entry = Mock(side_effect=mock_update_entry)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert updated_version == 4
        assert CONF_PROVIDER_API_KEYS in updated_data
        assert (
            updated_data[CONF_PROVIDER_API_KEYS][PROVIDER_GOOGLE]
            == "test_google_api_key"
        )
        assert CONF_GOOGLE_PLACES_API_KEY not in updated_data
        assert "other_config" in updated_data
        assert updated_data["other_config"] == "value"

        # Verify that the migrated key can be accessed the new way
        # (simulating how tools would access it)
        config_data = {**updated_data, **updated_options}
        provider_keys = config_data.get(CONF_PROVIDER_API_KEYS) or {}
        api_key = provider_keys.get(PROVIDER_GOOGLE, "")
        assert api_key == "test_google_api_key"


class TestPlacesProviderMigration:
    """Test the version 3 to 4 migration of google_places_enabled."""

    @pytest.fixture
    def captured_update(self, hass: HomeAssistant) -> dict[str, Any]:
        """Replace async_update_entry with a capture of the final update."""
        captured: dict[str, Any] = {}

        def mock_update_entry(entry_obj: ConfigEntry, **kwargs: Any) -> None:
            captured.update(kwargs)

        hass.config_entries.async_update_entry = Mock(side_effect=mock_update_entry)
        return captured

    async def test_enabled_in_data_migrates_to_google_preserving_values(
        self, hass: HomeAssistant, captured_update: dict[str, Any]
    ) -> None:
        """google_places_enabled in data becomes the Google places provider."""
        data = {
            CONF_GOOGLE_PLACES_ENABLED: True,
            CONF_GOOGLE_PLACES_NUM_RESULTS: 7,
            CONF_GOOGLE_PLACES_LATITUDE: 40.1,
            CONF_GOOGLE_PLACES_LONGITUDE: -76.9,
            CONF_GOOGLE_PLACES_RADIUS: 25,
            CONF_GOOGLE_PLACES_RANKING: "Distance",
            CONF_PROVIDER_API_KEYS: {PROVIDER_GOOGLE: "test_google_api_key"},
            CONF_SEARCH_PROVIDER: "Brave",
            CONF_GOOGLE_ROUTES_ENABLED: True,
            "other_config": "value",
        }
        entry = MockConfigEntry(
            domain=DOMAIN, entry_id="test_entry", version=3, data=data, options={}
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert captured_update["version"] == 4
        new_data = captured_update["data"]
        assert new_data[CONF_PLACES_PROVIDER] == CONF_PLACES_PROVIDER_GOOGLE
        assert CONF_GOOGLE_PLACES_ENABLED not in new_data
        assert CONF_GOOGLE_PLACES_ENABLED not in captured_update["options"]
        # Every other stored value survives untouched
        for key, value in data.items():
            if key == CONF_GOOGLE_PLACES_ENABLED:
                continue
            assert new_data[key] == value

    async def test_enabled_in_options_migrates_to_google(
        self, hass: HomeAssistant, captured_update: dict[str, Any]
    ) -> None:
        """The boolean is honoured from options too (options win at runtime)."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=3,
            data={CONF_GOOGLE_PLACES_NUM_RESULTS: 5},
            options={CONF_GOOGLE_PLACES_ENABLED: True},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        merged = {**captured_update["data"], **captured_update["options"]}
        assert merged[CONF_PLACES_PROVIDER] == CONF_PLACES_PROVIDER_GOOGLE
        assert CONF_GOOGLE_PLACES_ENABLED not in merged
        assert merged[CONF_GOOGLE_PLACES_NUM_RESULTS] == 5

    async def test_empty_options_selection_does_not_shadow_migration(
        self, hass: HomeAssistant, captured_update: dict[str, Any]
    ) -> None:
        """A stored empty places_provider in options must not shadow the result."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=3,
            data={CONF_GOOGLE_PLACES_ENABLED: True},
            options={CONF_PLACES_PROVIDER: None},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        merged = {**captured_update["data"], **captured_update["options"]}
        assert merged[CONF_PLACES_PROVIDER] == CONF_PLACES_PROVIDER_GOOGLE

    @pytest.mark.parametrize("data", [{CONF_GOOGLE_PLACES_ENABLED: False}, {}])
    async def test_not_enabled_gets_no_provider(
        self, hass: HomeAssistant, captured_update: dict[str, Any], data: dict
    ) -> None:
        """Places off (or never configured) stays off: no provider selected."""
        entry = MockConfigEntry(
            domain=DOMAIN, entry_id="test_entry", version=3, data=data, options={}
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert captured_update["version"] == 4
        merged = {**captured_update["data"], **captured_update["options"]}
        assert not merged.get(CONF_PLACES_PROVIDER)
        assert CONF_GOOGLE_PLACES_ENABLED not in merged

    async def test_existing_provider_is_left_untouched(
        self, hass: HomeAssistant, captured_update: dict[str, Any]
    ) -> None:
        """
        An entry that already picked a provider is not re-translated.

        Only the version bump and the boolean cleanup apply: the stored
        provider and every other value come through byte-equal.
        """
        data = {
            CONF_GOOGLE_PLACES_ENABLED: True,
            CONF_PROVIDER_API_KEYS: {PROVIDER_GOOGLE: "test_google_api_key"},
        }
        options = {CONF_PLACES_PROVIDER: CONF_PLACES_PROVIDER_OPENSTREETMAP}
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=3,
            data=dict(data),
            options=dict(options),
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert captured_update["version"] == 4
        expected_data = {
            key: value
            for key, value in data.items()
            if key != CONF_GOOGLE_PLACES_ENABLED
        }
        assert captured_update["data"] == expected_data
        assert captured_update["options"] == options

    async def test_provider_in_data_survives_options_shadow(
        self, hass: HomeAssistant, captured_update: dict[str, Any]
    ) -> None:
        """
        A provider stored in data is not overwritten because of options.

        The merged runtime view would hide the data provider behind the
        empty selection in options; with the old boolean still on, the
        migration must not "translate" the entry to Google — the chosen
        provider in data is preserved.
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=3,
            data={
                CONF_PLACES_PROVIDER: CONF_PLACES_PROVIDER_OPENSTREETMAP,
                CONF_GOOGLE_PLACES_ENABLED: True,
            },
            options={CONF_PLACES_PROVIDER: None},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert captured_update["version"] == 4
        assert (
            captured_update["data"][CONF_PLACES_PROVIDER]
            == CONF_PLACES_PROVIDER_OPENSTREETMAP
        )
        assert CONF_GOOGLE_PLACES_ENABLED not in captured_update["data"]

    async def test_v1_entry_migrates_through_the_whole_chain(
        self, hass: HomeAssistant
    ) -> None:
        """
        A version 1 entry ends at version 4 with every step applied.

        Uses the real async_update_entry so each step sees the previous
        step's stored result, exactly as Home Assistant runs it.
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=1,
            data={
                CONF_BRAVE_ENABLED: True,
                CONF_GOOGLE_PLACES_API_KEY: "test_google_api_key",
                CONF_GOOGLE_PLACES_ENABLED: True,
            },
            options={},
        )
        entry.add_to_hass(hass)

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert entry.version == 4
        # 1 -> 2: the Brave boolean became the search provider selector
        assert entry.data[CONF_SEARCH_PROVIDER] == CONF_SEARCH_PROVIDER_BRAVE
        assert CONF_BRAVE_ENABLED not in entry.data
        # 2 -> 3: the legacy places key moved into provider_api_keys
        assert (
            entry.data[CONF_PROVIDER_API_KEYS][PROVIDER_GOOGLE] == "test_google_api_key"
        )
        assert CONF_GOOGLE_PLACES_API_KEY not in entry.data
        # 3 -> 4: the enabled boolean became the Google places provider
        assert entry.data[CONF_PLACES_PROVIDER] == CONF_PLACES_PROVIDER_GOOGLE
        assert CONF_GOOGLE_PLACES_ENABLED not in entry.data

    async def test_v2_entry_chains_through_both_migrations(
        self, hass: HomeAssistant, captured_update: dict[str, Any]
    ) -> None:
        """A version 2 entry ends at version 4 with key and provider migrated."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=2,
            data={
                CONF_GOOGLE_PLACES_API_KEY: "test_google_api_key",
                CONF_GOOGLE_PLACES_ENABLED: True,
            },
            options={},
        )

        result = await async_migrate_entry(hass, entry)

        assert result is True
        assert captured_update["version"] == 4
        new_data = captured_update["data"]
        assert (
            new_data[CONF_PROVIDER_API_KEYS][PROVIDER_GOOGLE] == "test_google_api_key"
        )
        assert new_data[CONF_PLACES_PROVIDER] == CONF_PLACES_PROVIDER_GOOGLE
        assert CONF_GOOGLE_PLACES_ENABLED not in new_data

    async def test_migrating_a_current_entry_is_a_noop(
        self, hass: HomeAssistant
    ) -> None:
        """An already-migrated (version 4) entry is not updated again."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            version=4,
            data={CONF_PLACES_PROVIDER: CONF_PLACES_PROVIDER_GOOGLE},
            options={},
        )
        hass.config_entries.async_update_entry = Mock()

        result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()
