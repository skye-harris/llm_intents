"""Tests for the WeatherForecastTool."""

import datetime as dt
from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from freezegun import freeze_time
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from custom_components.llm_intents.const import DOMAIN
from custom_components.llm_intents.weather import (
    ForecastRetrievalError,
    WeatherAttribute,
    WeatherEntityNotFoundError,
    WeatherForecastTool,
    _build_attributes,
    _friendly_precipitation_chance,
)
from tests.utils import MockContext


@pytest.fixture
def tool(mock_hass: HomeAssistant) -> WeatherForecastTool:
    """Return an instance of the WeatherForecastTool."""
    return WeatherForecastTool({}, mock_hass)


@pytest.mark.parametrize(
    ("precipitation_chance", "expected"),
    [
        (0, "none"),
        (1, "very unlikely"),
        (5, "very unlikely"),
        (6, "unlikely"),
        (15, "unlikely"),
        (16, "possible"),
        (30, "possible"),
        (31, "moderate"),
        (50, "moderate"),
        (51, "likely"),
        (70, "likely"),
        (71, "very likely"),
        (85, "very likely"),
        (95, "extremely likely"),
        (100, "almost guaranteed"),
        (101, "almost guaranteed"),
    ],
)
def test_friendly_precipitation_chance(
    precipitation_chance: int, expected: str
) -> None:
    """Test precipitation chance categorization at various thresholds."""
    result = _friendly_precipitation_chance(precipitation_chance)
    assert result == expected


def test_build_attributes() -> None:
    """Test building attributes function with and without a formatter provided."""
    weather_data = {"precipitation_probability": 75, "condition": "Sunny"}
    attributes = [
        WeatherAttribute(
            name="Condition",
            key="condition",
            formatter=None,
        ),
        WeatherAttribute(
            name="Chance of Precipitation",
            key="precipitation_probability",
            formatter=_friendly_precipitation_chance,
        ),
    ]
    # Set the name attribute after creation
    result = _build_attributes(attributes, weather_data)

    assert result[0] == "  Condition: Sunny"
    assert result[1] == "  Chance of Precipitation: very likely"


def test_build_attributes_missing_key() -> None:
    """Test that missing keys are skipped."""
    weather_data = {}
    attributes = [
        WeatherAttribute(name="Condition", key="condition", formatter=None),
    ]
    result = _build_attributes(attributes, weather_data)
    assert result == []


# =============================================================================
# _find_target_date() tests
# =============================================================================


@pytest.mark.parametrize(
    ("date_range", "expected_delta_days"),
    [
        ("today", 0),
        ("tomorrow", 1),
        ("tuesday", 5),
        ("wednesday", 6),
        ("thursday", 0),
        ("friday", 1),
        ("saturday", 2),
        ("sunday", 3),
    ],
)
@pytest.mark.freeze_time("2026-01-01")
def test_find_target_date_relative(
    date_range: str,
    expected_delta_days: int,
) -> None:
    """Test finding target date for relative expressions."""
    result = WeatherForecastTool._find_target_date(date_range)
    assert isinstance(result, date)
    assert result == datetime.now().astimezone().date() + timedelta(
        days=expected_delta_days
    )


def test_find_target_date_invalid() -> None:
    """Test that invalid date ranges return None."""
    result = WeatherForecastTool._find_target_date("next week")
    assert result is None


def test_find_target_date_explicit_now_different_timezone() -> None:
    """Test that _find_target_date respects the provided 'now' datetime."""
    now_utc = dt.datetime(2026, 1, 1, 23, 0, 0, tzinfo=dt.UTC)
    assert WeatherForecastTool._find_target_date("today", now_utc) == date(2026, 1, 1)

    # Same moment in UTC+2 is already Jan 2
    now_ahead = dt.datetime(2026, 1, 2, 1, 0, 0, tzinfo=dt.timezone(timedelta(hours=2)))
    assert WeatherForecastTool._find_target_date("today", now_ahead) == date(2026, 1, 2)


# =============================================================================
# _filter_forecast_by_day() tests
# =============================================================================


def test_filter_forecast_by_day_matches() -> None:
    """Test filtering forecast when entries match target date."""
    forecast = [
        {"datetime": "2026-05-01T12:00:00+00:00", "temperature": 20},
        {"datetime": "2026-05-03T12:00:00+00:00", "temperature": 22},
    ]
    target = date(2026, 5, 3)
    result = WeatherForecastTool._filter_forecast_by_day(forecast, target)
    assert len(result) == 1
    assert result[0]["temperature"] == 22


def test_filter_forecast_by_day_no_matches() -> None:
    """Test filtering forecast when no entries match target date."""
    forecast = [
        {"datetime": "2026-05-01T12:00:00+00:00", "temperature": 20},
    ]
    target = date(2026, 5, 3)
    result = WeatherForecastTool._filter_forecast_by_day(forecast, target)
    assert result == []


def test_filter_forecast_by_day_multiple_matches() -> None:
    """Test filtering forecast when multiple entries match target date."""
    forecast = [
        {"datetime": "2026-05-03T08:00:00+00:00", "temperature": 18},
        {"datetime": "2026-05-03T12:00:00+00:00", "temperature": 24},
        {"datetime": "2026-05-03T20:00:00+00:00", "temperature": 16},
    ]
    target = date(2026, 5, 3)
    result = WeatherForecastTool._filter_forecast_by_day(forecast, target)
    assert len(result) == 3


# =============================================================================
# _format_time() tests
# =============================================================================


@pytest.mark.parametrize(
    ("input_hour", "expected_output"),
    [
        (8, "9am"),
        (14, "3pm"),
        (0, "1am"),
        (12, "1pm"),
        (1, "2am"),
        (13, "2pm"),
        (23, "12am"),
    ],
)
def test_format_time(
    input_hour: int,
    expected_output: str,
) -> None:
    """Test formatting time - returns NEXT hour in local timezone."""
    # Mock datetime module to control timezone behavior
    with patch("custom_components.llm_intents.weather.datetime") as mock_dt:
        # Mock fromisoformat to return a mock datetime instance
        mock_datetime_instance = MagicMock()
        mock_dt.fromisoformat.return_value = mock_datetime_instance

        # Mock astimezone to return a datetime at the input hour
        mock_astimezone_result = dt.datetime(
            2026, 5, 3, input_hour, 0, 0, tzinfo=dt.UTC
        )
        mock_datetime_instance.astimezone.return_value = mock_astimezone_result

        result = WeatherForecastTool._format_time(
            f"2026-05-03T{input_hour:02d}:00:00+00:00"
        )
        assert result == expected_output


# =============================================================================
# _format_date() tests
# =============================================================================


@pytest.mark.freeze_time("2026-01-01")
def test_format_date_today() -> None:
    """Test formatting today's date."""
    # Use a date that is definitely in the future to avoid "today" ambiguity
    result = WeatherForecastTool._format_date("2026-06-01T12:00:00+00:00")
    assert "Today" not in result
    assert "Monday" in result  # 2026-06-01 is a Monday


@pytest.mark.freeze_time("2026-01-01")
def test_format_date_future() -> None:
    """Test formatting a future date."""
    # Use a date that is definitely in the future to avoid "today" ambiguity
    result = WeatherForecastTool._format_date("2026-06-15T12:00:00+00:00")
    assert "Today" not in result
    assert "Monday" in result  # 2026-06-15 is a Monday


@freeze_time("2026-01-01 23:00:00")
def test_format_om_date_with_timezone() -> None:
    """Test _format_om_date respects the target timezone for 'Today'."""
    # Local time is Jan 1 23:00 UTC; Jan 2 is not "today" locally
    result = WeatherForecastTool._format_om_date(date(2026, 1, 2))
    assert "Today" not in result
    assert "Friday" in result

    # In Europe/Stockholm (UTC+1 in Jan) it is already Jan 2 00:00
    result = WeatherForecastTool._format_om_date(date(2026, 1, 2), "Europe/Stockholm")
    assert "Today" in result


# =============================================================================
# has_twice_daily_data() tests
# =============================================================================


def test_has_twice_daily_data_entity_not_found(tool: WeatherForecastTool) -> None:
    """Test that WeatherEntityNotFoundError is raised when entity is not found."""
    # Create states mock before patching
    mock_states = MagicMock()
    mock_states.get.return_value = None
    tool.hass.states = mock_states
    with pytest.raises(WeatherEntityNotFoundError):
        tool.has_twice_daily_data("sensor.test_weather")


def test_has_twice_daily_data_not_supported(tool: WeatherForecastTool) -> None:
    """Test when entity exists but doesn't support twice-daily data."""
    mock_states = MagicMock()
    entity = MagicMock()
    entity.attributes = {"supported_features": 0}
    mock_states.get.return_value = entity
    tool.hass.states = mock_states
    result = tool.has_twice_daily_data("sensor.test_weather")
    assert not result


def test_has_twice_daily_data_supported(tool: WeatherForecastTool) -> None:
    """Test when entity supports twice-daily data."""
    mock_states = MagicMock()
    entity = MagicMock()
    entity.attributes = {
        "supported_features": WeatherEntityFeature.FORECAST_TWICE_DAILY
    }
    mock_states.get.return_value = entity
    tool.hass.states = mock_states
    result = tool.has_twice_daily_data("sensor.test_weather")
    assert result


# =============================================================================
# _get_current_temperature_sensor_data() tests
# =============================================================================


@pytest.mark.parametrize(
    ("state", "expected_result"),
    [
        ("22.5", "- Time: current\n  Temperature: 22°C"),
        ("23.9", "- Time: current\n  Temperature: 24°C"),
        ("0.0", "- Time: current\n  Temperature: 0°C"),
        ("100.1", "- Time: current\n  Temperature: 100°C"),
        ("unknown", ""),
        ("unavailable", ""),
        ("invalid", None),
        ("-5.7", "- Time: current\n  Temperature: -6°C"),
        ("22", "- Time: current\n  Temperature: 22°C"),
        ("-10.0", "- Time: current\n  Temperature: -10°C"),
    ],
)
def test_get_current_temperature_sensor_data(
    tool: WeatherForecastTool,
    mock_hass: HomeAssistant,
    state: str,
    expected_result: str,
) -> None:
    """Test getting current temperature sensor data with various states."""
    mock_states = MagicMock()
    entity = MagicMock()
    entity.state = state
    entity.attributes = {"unit_of_measurement": UnitOfTemperature.CELSIUS}
    mock_states.get.return_value = entity
    tool.hass.states = mock_states
    result = tool._get_current_temperature_sensor_data(
        mock_hass,
        "sensor.temperature",
        UnitOfTemperature.CELSIUS,
    )
    assert result == expected_result


# =============================================================================
# _get_daily_forecast() tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_daily_forecast_with_target_date(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test getting daily forecast with a target date."""
    tool: WeatherForecastTool  # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    forecast_data = [
        {
            "datetime": "2026-05-01T12:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
            "precipitation_probability": 30,
        },
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Cloudy",
            "precipitation_probability": 50,
        },
    ]

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": forecast_data}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    target_date = date(2026, 5, 3)
    result = await tool._get_daily_forecast(
        mock_hass,
        "sensor.test_weather",
        target_date,
        UnitOfTemperature.CELSIUS,
    )

    assert "Sunday" in result  # 2026-05-03 is a Sunday
    assert "Cloudy" in result
    assert "Precipitation: moderate" in result


@pytest.mark.asyncio
async def test_get_daily_forecast_without_target_date(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test getting daily forecast without a target date (all days)."""
    # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    forecast_data = [
        {
            "datetime": "2026-05-01T12:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
            "precipitation_probability": 30,
        },
        {
            "datetime": "2026-05-02T12:00:00+00:00",
            "temperature": 21,
            "templow": 16,
            "condition": "Partly Cloudy",
            "precipitation_probability": 40,
        },
    ]

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": forecast_data}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    result = await tool._get_daily_forecast(
        mock_hass,
        "sensor.test_weather",
        None,
        UnitOfTemperature.CELSIUS,
    )

    assert len(result.split("\n")) >= 2
    assert "Sunny" in result
    assert "Partly Cloudy" in result


@pytest.mark.asyncio
async def test_get_daily_forecast_no_forecast(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test when no forecast data is available."""
    # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": []}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    with pytest.raises(ForecastRetrievalError):
        await tool._get_daily_forecast(
            mock_hass,
            "sensor.test_weather",
            None,
            UnitOfTemperature.CELSIUS,
        )


# =============================================================================
# _get_twice_daily_forecast() tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_twice_daily_forecast(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test getting twice-daily forecast."""
    # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    forecast_data = [
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
            "precipitation_probability": 30,
            "is_daytime": True,
        },
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 16,
            "templow": 12,
            "condition": "Clear",
            "precipitation_probability": 10,
            "is_daytime": False,
        },
    ]

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": forecast_data}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    target_date = date(2026, 5, 3)
    result = await tool._get_twice_daily_forecast(
        mock_hass,
        "sensor.test_weather",
        target_date,
        UnitOfTemperature.CELSIUS,
    )

    assert "daytime" in result
    assert "nighttime" in result
    assert "Sunny" in result
    assert "Clear" in result


@pytest.mark.asyncio
async def test_get_twice_daily_forecast_no_twice_daily_support(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test that forecast is still returned even if entity doesn't support twice-daily."""
    # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    forecast_data = [
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
            "precipitation_probability": 30,
            "is_daytime": True,
        },
    ]

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": forecast_data}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    target_date = date(2026, 5, 3)
    result = await tool._get_twice_daily_forecast(
        mock_hass,
        "sensor.test_weather",
        target_date,
        UnitOfTemperature.CELSIUS,
    )

    assert "Sunny" in result


@pytest.mark.asyncio
async def test_get_twice_daily_forecast_no_forecast(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test when no twice-daily forecast data is available."""
    # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": []}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    with pytest.raises(ForecastRetrievalError):
        await tool._get_twice_daily_forecast(
            mock_hass,
            "sensor.test_weather",
            None,
            UnitOfTemperature.CELSIUS,
        )


# =============================================================================
# _get_hourly_forecast() tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_hourly_forecast(
    tool: WeatherForecastTool,
    mock_hass: HomeAssistant,
) -> None:
    """Test getting hourly forecast."""
    # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    forecast_data = [
        {
            "datetime": "2026-05-03T06:00:00+00:00",
            "temperature": 18,
            "condition": "Partly Cloudy",
            "precipitation_probability": 20,
        },
        {
            "datetime": "2026-05-03T07:00:00+00:00",
            "temperature": 20,
            "condition": "Sunny",
            "precipitation_probability": 10,
        },
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 25,
            "condition": "Sunny",
            "precipitation_probability": 0,
        },
        {
            "datetime": "2026-05-03T18:00:00+00:00",
            "temperature": 22,
            "condition": "Cloudy",
            "precipitation_probability": 40,
        },
    ]

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": forecast_data}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    target_date = date(2026, 5, 3)

    # Mock datetime to control timezone behavior
    with patch("custom_components.llm_intents.weather.datetime") as mock_dt:
        mock_dt_instance = mock_dt.return_value

        # Mock astimezone to return UTC timezone (no offset) so dates match
        mock_dt_instance.astimezone.return_value = dt.datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=dt.UTC
        )
        mock_dt_instance.now.return_value = dt.datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=dt.UTC
        )

        # Mock fromisoformat to return a UTC datetime at noon so it stays
        # on the same day even after timezone conversion.
        mock_dt.fromisoformat.return_value = dt.datetime(
            2026, 5, 3, 12, 0, 0, tzinfo=dt.UTC
        )

        result = await tool._get_hourly_forecast(
            mock_hass,
            "sensor.test_weather",
            target_date,
            UnitOfTemperature.CELSIUS,
        )

        assert "Partly Cloudy" in result
        assert "Sunny" in result
        assert "Cloudy" in result
        assert "Precipitation: possible" in result  # 20% is "possible"
        assert "Precipitation: unlikely" in result  # 10% is "unlikely"
        assert "Precipitation: none" in result  # 0% is "none"
        assert "Temperature: 18" in result
        assert "Temperature: 25" in result
        # Verify all 4 hourly entries are present
        assert result.count("- Time:") == 4


@pytest.mark.asyncio
async def test_get_hourly_forecast_no_forecast(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test when no hourly forecast data is available."""
    # Set up mock hass data and states
    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": []}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    target_date = date(2026, 5, 3)
    with pytest.raises(ForecastRetrievalError):
        await tool._get_hourly_forecast(
            mock_hass,
            "sensor.test_weather",
            target_date,
            UnitOfTemperature.CELSIUS,
        )


# =============================================================================
# async_call() integration tests
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_daily_forecast(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call with daily forecast."""
    tool_input = llm.ToolInput(
        tool_args={"range": "tomorrow"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-04T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": forecast_data}}
    mock_services = MagicMock()
    tool.hass.services = mock_services
    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.attributes = {"supported_features": 0}  # Not twice daily
    mock_states.get.return_value = mock_entity
    tool.hass.states = mock_states

    # Set up mock hass data and config_entries
    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_daily_entity": "sensor.test_weather",
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    # Make async_call return an awaitable coroutine
    async def mock_async_call(*args: object, **kwargs: Any) -> dict:
        return {"sensor.test_weather": {"forecast": forecast_data}}

    mock_services.async_call = mock_async_call

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Sunny" in result
    assert "Precipitation: possible" in result  # 30% is "possible"


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_with_temperature_sensor(mock_hass: HomeAssistant) -> None:
    """Test async_call with current temperature sensor included."""
    tool = WeatherForecastTool(
        {
            "current_temperature_entity": "sensor.temperature",
        },
        mock_hass,
    )

    tool_input = llm.ToolInput(
        tool_args={"range": "today"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": forecast_data}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    mock_states = MagicMock()
    entity = MagicMock()
    entity.state = "23"
    entity.attributes = {
        "supported_features": 0,
        "unit_of_measurement": UnitOfTemperature.CELSIUS,
    }
    mock_states.get.return_value = entity
    tool.hass.states = mock_states

    # Set up mock hass data and config_entries
    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_hourly_entity": "sensor.test_weather",
                "current_temperature_entity": "sensor.temperature",
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "current" in result
    assert "Temperature: 23°C" in result

    # Verify the service was called for hourly forecast (not daily)
    mock_services.async_call.assert_called_once_with(
        "weather",
        "get_forecasts",
        {"entity_id": "sensor.test_weather", "type": "hourly"},
        blocking=True,
        return_response=True,
    )


@pytest.mark.asyncio
async def test_async_call_no_forecast_available(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call when no forecast is available."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week"},
        tool_name="get_weather_forecast",
    )

    mock_service = AsyncMock(side_effect=ForecastRetrievalError)
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    # Mock entity as existing but not twice-daily
    mock_entity = MagicMock()
    mock_entity.attributes = {"supported_features": 0}
    tool.hass.states = MagicMock()
    tool.hass.states.get.return_value = mock_entity

    # Set up mock hass data and config_entries
    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_daily_entity": "sensor.test_weather",
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    # When forecast retrieval fails, return error message
    assert "Error retrieving weather forecast" in result.get("error", "")


@pytest.mark.asyncio
async def test_async_call_error_handling(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call error handling."""
    tool_input = llm.ToolInput(
        tool_args={"range": "today"},
        tool_name="get_weather_forecast",
    )

    mock_service = AsyncMock(side_effect=Exception("Service error"))
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services
    tool.hass.states = MagicMock()
    tool.hass.states.get.return_value = None

    # Set up mock hass data and config_entries
    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_daily_entity": "sensor.test_weather",
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "error" in result
    assert "Error retrieving weather forecast" in result["error"]


# =============================================================================
# Unit resolution and conversion tests
# =============================================================================


def test_resolve_target_unit_from_arg(tool: WeatherForecastTool) -> None:
    """Test that an explicit unit argument is resolved correctly."""
    assert tool._resolve_target_unit("celsius") == UnitOfTemperature.CELSIUS
    assert tool._resolve_target_unit("fahrenheit") == UnitOfTemperature.FAHRENHEIT


def test_resolve_target_unit_default(tool: WeatherForecastTool) -> None:
    """Test that the default comes from Home Assistant settings."""
    # The mock_hass fixture sets this to CELSIUS
    assert tool._resolve_target_unit(None) == UnitOfTemperature.CELSIUS


def test_convert_temperature_same_unit() -> None:
    """Test that no conversion happens when units match."""
    result = WeatherForecastTool._convert_temperature(
        22.0,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.CELSIUS,
    )
    assert result == 22


def test_convert_temperature_c_to_f() -> None:
    """Test Celsius to Fahrenheit conversion."""
    result = WeatherForecastTool._convert_temperature(
        0.0,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.FAHRENHEIT,
    )
    assert result == 32


def test_convert_temperature_f_to_c() -> None:
    """Test Fahrenheit to Celsius conversion."""
    result = WeatherForecastTool._convert_temperature(
        32.0,
        UnitOfTemperature.FAHRENHEIT,
        UnitOfTemperature.CELSIUS,
    )
    assert result == 0


def test_convert_temperature_unknown_source() -> None:
    """Test that unknown source units are treated as already in target unit."""
    result = WeatherForecastTool._convert_temperature(
        22.0,
        "some_unknown_unit",
        UnitOfTemperature.CELSIUS,
    )
    assert result == 22


def test_format_single_temperature(tool: WeatherForecastTool) -> None:
    """Test single temperature formatting includes the unit symbol."""
    result = tool._format_single_temperature(
        22.5,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.CELSIUS,
    )
    assert result == "22°C"


def test_format_temperature_default(tool: WeatherForecastTool) -> None:
    """Test temperature formatting with show_both_units off (default)."""
    tool.show_both_units = False
    result = tool._format_temperature(
        22.0,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.CELSIUS,
    )
    assert result == "22°C"


def test_format_temperature_both_units_celsius(tool: WeatherForecastTool) -> None:
    """Test temperature formatting with show_both_units on (HA default Celsius)."""
    tool.show_both_units = True
    result = tool._format_temperature(
        22.0,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.CELSIUS,
    )
    assert result == "22°C (72°F)"


def test_format_temperature_both_units_fahrenheit(tool: WeatherForecastTool) -> None:
    """Test temperature formatting with show_both_units on (HA default Fahrenheit)."""
    tool.show_both_units = True
    result = tool._format_temperature(
        72.0,
        UnitOfTemperature.FAHRENHEIT,
        UnitOfTemperature.FAHRENHEIT,
    )
    assert result == "72°F (22°C)"


def test_format_temperature_range_default(tool: WeatherForecastTool) -> None:
    """Test temperature range formatting with show_both_units off."""
    tool.show_both_units = False
    result = tool._format_temperature_range(
        22.0,
        15.0,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.CELSIUS,
    )
    assert result == "15°C - 22°C"


def test_format_temperature_range_both_units(tool: WeatherForecastTool) -> None:
    """Test temperature range formatting with show_both_units on."""
    tool.show_both_units = True
    result = tool._format_temperature_range(
        22.0,
        15.0,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.CELSIUS,
    )
    assert result == "15°C - 22°C (59°F - 72°F)"


def test_format_temperature_range_no_low(tool: WeatherForecastTool) -> None:
    """Test temperature range formatting when low is None."""
    tool.show_both_units = True
    result = tool._format_temperature_range(
        22.0,
        None,
        UnitOfTemperature.CELSIUS,
        UnitOfTemperature.CELSIUS,
    )
    assert result == "22°C (72°F)"


# =============================================================================
# Open-Meteo location tests
# =============================================================================


@pytest.mark.asyncio
@patch("custom_components.llm_intents.weather.async_get_clientsession")
async def test_async_call_with_location(
    mock_get_session: MagicMock,
    tool: WeatherForecastTool,
    mock_hass: HomeAssistant,
) -> None:
    """Test async_call routes to Open-Meteo when a location is provided."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week", "location": "Paris"},
        tool_name="get_weather_forecast",
    )

    # Mock geocoding response
    geo_response = AsyncMock()
    geo_response.status = 200
    geo_response.json = AsyncMock(
        return_value={
            "results": [
                {
                    "name": "Paris",
                    "admin1": "Île-de-France",
                    "country": "France",
                    "latitude": 48.85,
                    "longitude": 2.35,
                }
            ]
        }
    )

    # Mock forecast response
    forecast_response = AsyncMock()
    forecast_response.status = 200
    forecast_response.json = AsyncMock(
        return_value={
            "daily": {
                "time": ["2026-05-03"],
                "temperature_2m_max": [18.0],
                "temperature_2m_min": [10.0],
                "weather_code": [1],
                "precipitation_probability_max": [20],
            }
        }
    )

    session = Mock()

    def _mock_get(*args: object, **kwargs: Any) -> MockContext:
        # First call is geocoding, second is forecast
        if "geocoding" in str(args[0]):
            return MockContext(geo_response)
        return MockContext(forecast_response)

    session.get = Mock(side_effect=_mock_get)
    mock_get_session.return_value = session

    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Paris" in result
    assert "18°C" in result
    assert "10°C" in result
    assert "mainly clear" in result


@pytest.mark.asyncio
@patch("custom_components.llm_intents.weather.async_get_clientsession")
async def test_async_call_location_different_timezone(
    mock_get_session: MagicMock,
    tool: WeatherForecastTool,
    mock_hass: HomeAssistant,
) -> None:
    """Test location forecast when target timezone is ahead of local time."""
    # Freeze to 23:00 UTC on Jan 1; in Stockholm (UTC+1) it is already Jan 2.
    with freeze_time(dt.datetime(2026, 1, 1, 23, 0, 0, tzinfo=dt.UTC)):
        tool_input = llm.ToolInput(
            tool_args={"range": "today", "location": "Stockholm", "hourly": False},
            tool_name="get_weather_forecast",
        )

        geo_response = AsyncMock()
        geo_response.status = 200
        geo_response.json = AsyncMock(
            return_value={
                "results": [
                    {
                        "name": "Stockholm",
                        "admin1": "Stockholm County",
                        "country": "Sweden",
                        "latitude": 59.33,
                        "longitude": 18.07,
                        "timezone": "Europe/Stockholm",
                    }
                ]
            }
        )

        # Stockholm is already on Jan 2, so API returns Jan 2 data
        forecast_response = AsyncMock()
        forecast_response.status = 200
        forecast_response.json = AsyncMock(
            return_value={
                "daily": {
                    "time": ["2026-01-02"],
                    "temperature_2m_max": [5.0],
                    "temperature_2m_min": [-2.0],
                    "weather_code": [3],
                    "precipitation_probability_max": [30],
                }
            }
        )

        session = Mock()

        def _mock_get(*args: object, **kwargs: Any) -> MockContext:
            if "geocoding" in str(args[0]):
                return MockContext(geo_response)
            return MockContext(forecast_response)

        session.get = Mock(side_effect=_mock_get)
        mock_get_session.return_value = session

        mock_entry = MagicMock(options={})
        mock_hass.data = {DOMAIN: {"config": {}}}
        mock_hass.config_entries = MagicMock()
        mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

        result = await tool.async_call(
            mock_hass,
            tool_input,
            MagicMock(spec=llm.LLMContext),
        )

    assert "Stockholm" in result
    assert "5°C" in result
    assert "Today" in result


@pytest.mark.asyncio
@patch("custom_components.llm_intents.weather.async_get_clientsession")
async def test_async_call_location_not_found(
    mock_get_session: MagicMock,
    tool: WeatherForecastTool,
    mock_hass: HomeAssistant,
) -> None:
    """Test error handling when Open-Meteo geocoding returns no results."""
    tool_input = llm.ToolInput(
        tool_args={"range": "today", "location": "NonexistentPlaceXYZ"},
        tool_name="get_weather_forecast",
    )

    geo_response = AsyncMock()
    geo_response.status = 200
    geo_response.json = AsyncMock(return_value={"results": []})

    session = Mock()
    session.get = Mock(return_value=MockContext(geo_response))
    mock_get_session.return_value = session

    mock_entry = MagicMock(options={})
    mock_hass.data = {DOMAIN: {"config": {}}}
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "error" in result
    assert "Could not find weather data" in result["error"]


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_with_unit_override(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call converts temperatures when unit is overridden."""
    tool_input = llm.ToolInput(
        tool_args={"range": "tomorrow", "unit": "fahrenheit"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-04T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    async def mock_async_call(*args: object, **kwargs: Any) -> dict:
        return {"sensor.test_weather": {"forecast": forecast_data}}

    mock_services = MagicMock()
    mock_services.async_call = mock_async_call
    tool.hass.services = mock_services

    # Entity reports in Celsius
    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.attributes = {
        "supported_features": 0,
        "temperature_unit": UnitOfTemperature.CELSIUS,
    }
    mock_states.get.return_value = mock_entity
    tool.hass.states = mock_states

    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_daily_entity": "sensor.test_weather",
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Sunny" in result
    # 22°C -> 72°F, 17°C -> 63°F
    assert "63°F - 72°F" in result


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_show_both_units(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call returns both units when show_both_units is enabled."""
    tool_input = llm.ToolInput(
        tool_args={"range": "tomorrow"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-04T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    async def mock_async_call(*args: object, **kwargs: Any) -> dict:
        return {"sensor.test_weather": {"forecast": forecast_data}}

    mock_services = MagicMock()
    mock_services.async_call = mock_async_call
    tool.hass.services = mock_services

    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.attributes = {
        "supported_features": 0,
        "temperature_unit": UnitOfTemperature.CELSIUS,
    }
    mock_states.get.return_value = mock_entity
    tool.hass.states = mock_states

    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_daily_entity": "sensor.test_weather",
                "weather_show_both_units": True,
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Sunny" in result
    # Default unit is Celsius, so primary is Celsius, secondary is Fahrenheit
    assert "17°C - 22°C (63°F - 72°F)" in result


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_explicit_unit_ignores_show_both_units(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call returns only requested unit even when show_both_units is enabled."""
    tool_input = llm.ToolInput(
        tool_args={"range": "tomorrow", "unit": "fahrenheit"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-04T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    async def mock_async_call(*args: object, **kwargs: Any) -> dict:
        return {"sensor.test_weather": {"forecast": forecast_data}}

    mock_services = MagicMock()
    mock_services.async_call = mock_async_call
    tool.hass.services = mock_services

    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.attributes = {
        "supported_features": 0,
        "temperature_unit": UnitOfTemperature.CELSIUS,
    }
    mock_states.get.return_value = mock_entity
    tool.hass.states = mock_states

    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_daily_entity": "sensor.test_weather",
                "weather_show_both_units": True,
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Sunny" in result
    # Explicit fahrenheit request should NOT include both Celsius and Fahrenheit
    assert "63°F - 72°F" in result
    assert "°C" not in result


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_hourly_explicit_true(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call uses hourly when explicitly requested."""
    tool_input = llm.ToolInput(
        tool_args={"range": "today", "hourly": True},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 22,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(
        return_value={"sensor.test_weather": {"forecast": forecast_data}}
    )
    tool.hass.services = mock_services

    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.attributes = {"supported_features": 0}
    mock_states.get.return_value = mock_entity
    tool.hass.states = mock_states

    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_hourly_entity": "sensor.test_weather",
                "weather_daily_entity": "sensor.daily_weather",
                "weather_hourly_default": False,
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Sunny" in result
    # hourly=True should override the config default of False
    mock_services.async_call.assert_called_once_with(
        "weather",
        "get_forecasts",
        {"entity_id": "sensor.test_weather", "type": "hourly"},
        blocking=True,
        return_response=True,
    )


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_hourly_explicit_false(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call uses daily when hourly=False even with config default True."""
    tool_input = llm.ToolInput(
        tool_args={"range": "today", "hourly": False},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(
        return_value={"sensor.daily_weather": {"forecast": forecast_data}}
    )
    tool.hass.services = mock_services

    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.attributes = {"supported_features": 0}
    mock_states.get.return_value = mock_entity
    tool.hass.states = mock_states

    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_hourly_entity": "sensor.test_weather",
                "weather_daily_entity": "sensor.daily_weather",
                "weather_hourly_default": True,
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Sunny" in result
    # hourly=False should override config default and call daily entity
    mock_services.async_call.assert_called_once_with(
        "weather",
        "get_forecasts",
        {"entity_id": "sensor.daily_weather", "type": "daily"},
        blocking=True,
        return_response=True,
    )


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_hourly_config_default_false(
    tool: WeatherForecastTool, mock_hass: HomeAssistant
) -> None:
    """Test async_call uses daily when config hourly default is False and no arg given."""
    tool_input = llm.ToolInput(
        tool_args={"range": "today"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-03T12:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
        }
    ]

    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(
        return_value={"sensor.daily_weather": {"forecast": forecast_data}}
    )
    tool.hass.services = mock_services

    mock_states = MagicMock()
    mock_entity = MagicMock()
    mock_entity.attributes = {"supported_features": 0}
    mock_states.get.return_value = mock_entity
    tool.hass.states = mock_states

    mock_entry = MagicMock(options={})
    mock_hass.data = {
        DOMAIN: {
            "config": {
                "weather_hourly_entity": "sensor.test_weather",
                "weather_daily_entity": "sensor.daily_weather",
                "weather_hourly_default": False,
            },
        },
    }
    mock_hass.config_entries = MagicMock()
    mock_hass.config_entries.async_entries = MagicMock(return_value=[mock_entry])

    result = await tool.async_call(
        mock_hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert "Sunny" in result
    # No hourly arg and config default is False -> daily forecast
    mock_services.async_call.assert_called_once_with(
        "weather",
        "get_forecasts",
        {"entity_id": "sensor.daily_weather", "type": "daily"},
        blocking=True,
        return_response=True,
    )
