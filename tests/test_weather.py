"""Tests for the WeatherForecastTool."""

import datetime as dt
from datetime import date, datetime, timedelta
from http import HTTPStatus
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.llm import ToolResult
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant.common import MockConfigEntry

from custom_components.llm_intents.const import DOMAIN
from custom_components.llm_intents.weather import (
    OPEN_METEO_GEOCODING_URL,
    ForecastRetrievalError,
    WeatherAttribute,
    WeatherEntityNotFoundError,
    WeatherForecastTool,
    _build_attributes,
    _format_temperature,
    _format_temperature_range,
    _friendly_precipitation_chance,
)

from .utils import MockContext, mock_response


@pytest.fixture
def tool(hass: HomeAssistant) -> WeatherForecastTool:
    """Return an instance of the WeatherForecastTool."""
    return WeatherForecastTool({}, hass)


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


def test_build_attributes_none_value_and_missing_key() -> None:
    """Test that None values are skipped (not formatted or included) and missing keys are also skipped."""
    weather_data = {
        "condition": "Sunny",
        "precipitation_probability": None,
        # "wind_speed" is intentionally absent to test missing key handling
    }
    attributes = [
        WeatherAttribute(name="Condition", key="condition", formatter=None),
        WeatherAttribute(
            name="Chance of Precipitation",
            key="precipitation_probability",
            formatter=_friendly_precipitation_chance,
        ),
        WeatherAttribute(name="Wind Speed", key="wind_speed", formatter=None),
    ]
    result = _build_attributes(attributes, weather_data)

    assert len(result) == 1
    assert result[0] == "  Condition: Sunny"
    # precipitation_probability with None value should be skipped
    assert not any("Precipitation" in line for line in result)
    # wind_speed key is missing so should also be skipped
    assert not any("Wind Speed" in line for line in result)


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


# =============================================================================
# _filter_forecast_by_day() tests
# =============================================================================


def test_filter_forecast_by_day_matches() -> None:
    """Test filtering forecast when entries match target date."""
    forecast = [
        {"datetime": "2026-05-01T00:00:00+00:00", "temperature": 20},
        {"datetime": "2026-05-03T00:00:00+00:00", "temperature": 22},
    ]
    target = date(2026, 5, 3)
    result = WeatherForecastTool._filter_forecast_by_day(forecast, target)
    assert len(result) == 1
    assert result[0]["temperature"] == 22


def test_filter_forecast_by_day_no_matches() -> None:
    """Test filtering forecast when no entries match target date."""
    forecast = [
        {"datetime": "2026-05-01T00:00:00+00:00", "temperature": 20},
    ]
    target = date(2026, 5, 3)
    result = WeatherForecastTool._filter_forecast_by_day(forecast, target)
    assert result == []


def test_filter_forecast_by_day_multiple_matches() -> None:
    """Test filtering forecast when multiple entries match target date."""
    forecast = [
        {"datetime": "2026-05-03T08:00:00+00:00", "temperature": 18},
        {"datetime": "2026-05-03T12:00:00+00:00", "temperature": 24},
        {"datetime": "2026-05-03T04:00:00+00:00", "temperature": 16},
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
    result = WeatherForecastTool._format_date("2026-06-01T00:00:00+00:00")
    assert "Today" not in result
    assert "Monday" in result  # 2026-06-01 is a Monday


@pytest.mark.freeze_time("2026-01-01")
def test_format_date_future() -> None:
    """Test formatting a future date."""
    # Use a date that is definitely in the future to avoid "today" ambiguity
    result = WeatherForecastTool._format_date("2026-06-15T00:00:00+00:00")
    assert "Today" not in result
    assert "Monday" in result  # 2026-06-15 is a Monday


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
        ("22.5", "- Time: current\n  Temperature: 22"),
        ("23.9", "- Time: current\n  Temperature: 24"),
        ("0.0", "- Time: current\n  Temperature: 0"),
        ("100.1", "- Time: current\n  Temperature: 100"),
        ("unknown", ""),
        ("unavailable", ""),
        ("invalid", None),
        ("-5.7", "- Time: current\n  Temperature: -6"),
        ("22", "- Time: current\n  Temperature: 22"),
        ("-10.0", "- Time: current\n  Temperature: -10"),
    ],
)
def test_get_current_temperature_sensor_data(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
    state: str,
    expected_result: str,
) -> None:
    """Test getting current temperature sensor data with various states."""
    mock_states = MagicMock()
    entity = MagicMock()
    entity.state = state
    mock_states.get.return_value = entity
    tool.hass.states = mock_states
    result = tool._get_current_temperature_sensor_data(hass, "sensor.temperature")
    assert result == expected_result


# =============================================================================
# _get_daily_forecast() tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_daily_forecast_with_target_date(
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test getting daily forecast with a target date."""
    tool: WeatherForecastTool  # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

    forecast_data = [
        {
            "datetime": "2026-05-01T00:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
            "precipitation_probability": 30,
        },
        {
            "datetime": "2026-05-03T00:00:00+00:00",
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
        hass,
        "sensor.test_weather",
        target_date,
    )

    assert "Sunday" in result  # 2026-05-03 is a Sunday
    assert "Cloudy" in result
    assert "Precipitation: moderate" in result


@pytest.mark.asyncio
async def test_get_daily_forecast_without_target_date(
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test getting daily forecast without a target date (all days)."""
    # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

    forecast_data = [
        {
            "datetime": "2026-05-01T00:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
            "precipitation_probability": 30,
        },
        {
            "datetime": "2026-05-02T00:00:00+00:00",
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

    result = await tool._get_daily_forecast(hass, "sensor.test_weather", None)

    assert len(result.split("\n")) >= 2
    assert "Sunny" in result
    assert "Partly Cloudy" in result


@pytest.mark.asyncio
async def test_get_daily_forecast_no_forecast(
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test when no forecast data is available."""
    # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": []}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    with pytest.raises(ForecastRetrievalError):
        await tool._get_daily_forecast(hass, "sensor.test_weather", None)


# =============================================================================
# _get_twice_daily_forecast() tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_twice_daily_forecast(
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test getting twice-daily forecast."""
    # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

    forecast_data = [
        {
            "datetime": "2026-05-03T00:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
            "precipitation_probability": 30,
            "is_daytime": True,
        },
        {
            "datetime": "2026-05-03T00:00:00+00:00",
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
        hass,
        "sensor.test_weather",
        target_date,
    )

    assert "daytime" in result
    assert "nighttime" in result
    assert "Sunny" in result
    assert "Clear" in result


@pytest.mark.asyncio
async def test_get_twice_daily_forecast_no_twice_daily_support(
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test that forecast is still returned even if entity doesn't support twice-daily."""
    # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

    forecast_data = [
        {
            "datetime": "2026-05-03T00:00:00+00:00",
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
        hass,
        "sensor.test_weather",
        target_date,
    )

    assert "Sunny" in result


@pytest.mark.asyncio
async def test_get_twice_daily_forecast_no_forecast(
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test when no twice-daily forecast data is available."""
    # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": []}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    with pytest.raises(ForecastRetrievalError):
        await tool._get_twice_daily_forecast(hass, "sensor.test_weather", None)


# =============================================================================
# _get_hourly_forecast() tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_hourly_forecast(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test getting hourly forecast."""
    # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

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
            2026, 5, 3, 6, 0, 0, tzinfo=dt.UTC
        )
        mock_dt_instance.now.return_value = dt.datetime(
            2026, 5, 3, 0, 0, 0, tzinfo=dt.UTC
        )

        # Mock fromisoformat to return a UTC datetime
        mock_dt.fromisoformat.return_value = dt.datetime(
            2026, 5, 3, 6, 0, 0, tzinfo=dt.UTC
        )

        result = await tool._get_hourly_forecast(
            hass,
            "sensor.test_weather",
            target_date,
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
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test when no hourly forecast data is available."""
    # Set up mock hass data and states
    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {DOMAIN: {"config": {}}}
    mock_entry.add_to_hass(hass)

    mock_service = AsyncMock()
    mock_service.return_value = {"sensor.test_weather": {"forecast": []}}
    mock_services = MagicMock()
    mock_services.async_call = mock_service
    tool.hass.services = mock_services

    target_date = date(2026, 5, 3)
    with pytest.raises(ForecastRetrievalError):
        await tool._get_hourly_forecast(hass, "sensor.test_weather", target_date)


# =============================================================================
# async_call() integration tests
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_daily_forecast(hass: HomeAssistant) -> None:
    """Test async_call with daily forecast."""
    tool = WeatherForecastTool(
        {"weather_daily_entity": "sensor.test_weather"},
        hass,
    )
    tool_input = llm.ToolInput(
        tool_args={"range": "tomorrow"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-04T00:00:00+00:00",
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

    async def mock_async_call(*args: object, **kwargs: Any) -> dict:
        return {"sensor.test_weather": {"forecast": forecast_data}}

    mock_services.async_call = mock_async_call

    result = await tool.async_call(
        hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )
    assert isinstance(result, ToolResult)

    assert "Sunny" in result.data["result"]
    assert "Precipitation: possible" in result.data["result"]  # 30% is "possible"


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_with_temperature_sensor(hass: HomeAssistant) -> None:
    """Test async_call with current temperature sensor included."""
    tool = WeatherForecastTool(
        {
            "weather_hourly_entity": "sensor.test_weather",
            "current_temperature_entity": "sensor.temperature",
        },
        hass,
    )

    tool_input = llm.ToolInput(
        tool_args={"range": "today"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-03T00:00:00+00:00",
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
    entity.attributes = {"supported_features": 0}  # Not twice daily
    mock_states.get.return_value = entity
    tool.hass.states = mock_states

    result = await tool.async_call(
        hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )
    assert isinstance(result, ToolResult)

    assert "current" in result.data["result"]
    assert "Temperature: 23" in result.data["result"]

    # Verify the service was called for hourly forecast (not daily)
    mock_services.async_call.assert_called_once_with(
        "weather",
        "get_forecasts",
        {"entity_id": "sensor.test_weather", "type": "hourly"},
        blocking=True,
        return_response=True,
    )


@pytest.mark.asyncio
async def test_async_call_no_forecast_available(hass: HomeAssistant) -> None:
    """Test async_call when no forecast is available."""
    tool = WeatherForecastTool(
        {"weather_daily_entity": "sensor.test_weather"},
        hass,
    )
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

    result = await tool.async_call(
        hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )
    assert isinstance(result, ToolResult)

    # When forecast retrieval fails, return error message
    assert "Error retrieving weather forecast" in result.data.get("error", "")


@pytest.mark.asyncio
async def test_async_call_error_handling(hass: HomeAssistant) -> None:
    """Test async_call error handling."""
    tool = WeatherForecastTool(
        {"weather_daily_entity": "sensor.test_weather"},
        hass,
    )
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

    result = await tool.async_call(
        hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )
    assert isinstance(result, ToolResult)

    assert "error" in result.data
    assert "Error retrieving weather forecast" in result.data["error"]


@pytest.mark.freeze_time("2026-01-01")
def test_format_date_returns_today() -> None:
    """Test formatting when the forecast date matches today."""
    result = WeatherForecastTool._format_date("2026-01-01T00:00:00+00:00")
    assert result == "Today (Thursday)"


@pytest.mark.asyncio
@pytest.mark.freeze_time("2026-05-03")
async def test_async_call_twice_daily_forecast(hass: HomeAssistant) -> None:
    """Test async_call takes the twice-daily forecast path."""
    tool = WeatherForecastTool(
        {"weather_daily_entity": "sensor.test_weather"},
        hass,
    )
    tool_input = llm.ToolInput(
        tool_args={"range": "tomorrow"},
        tool_name="get_weather_forecast",
    )

    forecast_data = [
        {
            "datetime": "2026-05-04T00:00:00+00:00",
            "temperature": 22,
            "templow": 17,
            "condition": "Sunny",
            "precipitation_probability": 30,
            "is_daytime": True,
        },
        {
            "datetime": "2026-05-04T00:00:00+00:00",
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

    mock_entity = MagicMock()
    mock_entity.attributes = {
        "supported_features": WeatherEntityFeature.FORECAST_TWICE_DAILY
    }
    tool.hass.states = MagicMock()
    tool.hass.states.get.return_value = mock_entity

    result = await tool.async_call(
        hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )
    assert isinstance(result, ToolResult)

    assert "daytime" in result.data["result"]
    assert "nighttime" in result.data["result"]
    assert "Sunny" in result.data["result"]
    assert "Clear" in result.data["result"]


@pytest.mark.asyncio
async def test_async_call_no_forecast_fallback(
    tool: WeatherForecastTool, hass: HomeAssistant
) -> None:
    """Test async_call returns fallback message when no forecast is available."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week"},
        tool_name="get_weather_forecast",
    )

    mock_entry = MockConfigEntry(domain=DOMAIN, options={})
    hass.data = {
        DOMAIN: {
            "config": {},
        },
    }
    mock_entry.add_to_hass(hass)

    result = await tool.async_call(
        hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )
    assert isinstance(result, ToolResult)

    assert (
        result.data["result"] == "No weather forecast available for the selected range"
    )


# =============================================================================
# Open-Meteo location forecast tests
# =============================================================================

PARIS_GEOCODING = {
    "results": [
        {
            "name": "Paris",
            "latitude": 48.85341,
            "longitude": 2.3488,
            "country": "France",
            "admin1": "Ile-de-France",
            "timezone": "Europe/Paris",
        },
    ],
}

DAILY_FORECAST = {
    "daily": {
        "time": ["2026-05-01", "2026-05-02"],
        "temperature_2m_max": [20.4, 23.6],
        "temperature_2m_min": [11.2, 13.8],
        "weather_code": [3, 61],
        "precipitation_probability_max": [10, 80],
    },
}

HOURLY_FORECAST = {
    "hourly": {
        "time": ["2026-05-01T08:00", "2026-05-01T09:00", "2026-05-02T08:00"],
        "temperature_2m": [12.4, 15.6, 9.1],
        "weather_code": [0, 2, 61],
        "precipitation_probability": [0, 20, 90],
    },
}


def mock_open_meteo_session(
    geocoding: dict,
    forecast: dict | None = None,
    *,
    geocoding_status: int = HTTPStatus.OK,
    forecast_status: int = HTTPStatus.OK,
) -> AsyncMock:
    """Create a mock session answering the geocoding and forecast endpoints."""
    session = AsyncMock()

    def mock_request(url: str, **kwargs: Any) -> MockContext:
        if url == OPEN_METEO_GEOCODING_URL:
            return MockContext(mock_response(geocoding_status, geocoding))
        return MockContext(mock_response(forecast_status, forecast or {}))

    session.get = Mock(side_effect=mock_request)
    return session


def patch_session(session: AsyncMock) -> Any:
    """Patch the weather tool's aiohttp session factory."""
    return patch(
        "custom_components.llm_intents.weather.async_get_clientsession",
        return_value=session,
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "clear"),
        (3, "cloudy"),
        (61, "slight rain"),
        (95, "thunderstorm"),
        ("61", "slight rain"),
        (None, None),
        (12345, None),
        ("not-a-code", None),
    ],
)
def test_condition_from_code(code: Any, expected: str | None) -> None:
    """Test that WMO codes map to condition wording, and unknowns to None."""
    assert WeatherForecastTool._condition_from_code(code) == expected


@pytest.mark.parametrize(
    ("place", "expected"),
    [
        (
            {"name": "Paris", "admin1": "Ile-de-France", "country": "France"},
            "Paris, Ile-de-France, France",
        ),
        # A region echoing the place name is not repeated.
        (
            {"name": "Tokyo", "admin1": "Tokyo", "country": "Japan"},
            "Tokyo, Japan",
        ),
        ({"name": "Perth", "country": "Australia"}, "Perth, Australia"),
        ({"name": "Atlantis"}, "Atlantis"),
        ({}, ""),
    ],
)
def test_format_location_label(place: dict, expected: str) -> None:
    """Test that a geocoded place is labelled without repetition or gaps."""
    assert WeatherForecastTool._format_location_label(place) == expected


def test_place_timezone_valid() -> None:
    """Test that a reported timezone is resolved."""
    result = WeatherForecastTool._place_timezone({"timezone": "Europe/Paris"})
    assert result == ZoneInfo("Europe/Paris")


@pytest.mark.parametrize(
    "place",
    [{}, {"timezone": None}, {"timezone": ""}, {"timezone": "Not/AZone"}],
)
def test_place_timezone_unusable(place: dict) -> None:
    """Test that a missing or unresolvable timezone yields None."""
    assert WeatherForecastTool._place_timezone(place) is None


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
def test_format_remote_date_today() -> None:
    """Test that the current date at the location is labelled as today."""
    place_tz = ZoneInfo("Europe/Paris")
    result = WeatherForecastTool._format_remote_date(date(2026, 5, 1), place_tz)
    assert result == "Today (Friday)"


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
def test_format_remote_date_other_day() -> None:
    """Test that other dates are labelled with just the weekday name."""
    place_tz = ZoneInfo("Europe/Paris")
    result = WeatherForecastTool._format_remote_date(date(2026, 5, 2), place_tz)
    assert result == "Saturday"


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
def test_format_remote_date_without_timezone() -> None:
    """Test that date labelling still works when no timezone was reported."""
    result = WeatherForecastTool._format_remote_date(date(2026, 5, 1), None)
    assert result == "Today (Friday)"


def test_find_target_date_uses_supplied_now() -> None:
    """Test that a supplied reference time resolves the day at that location."""
    # This instant is still 1 May in Los Angeles but already 2 May in Paris,
    # so the day resolved for "today" depends on the clock it is read against.
    instant = datetime(2026, 5, 1, 23, 30, tzinfo=ZoneInfo("America/Los_Angeles"))
    paris_instant = instant.astimezone(ZoneInfo("Europe/Paris"))

    assert WeatherForecastTool._find_target_date("today", instant) == date(2026, 5, 1)
    assert WeatherForecastTool._find_target_date(
        "today",
        paris_instant,
    ) == date(2026, 5, 2)


async def test_geocode_location_success(tool: WeatherForecastTool) -> None:
    """Test that geocoding returns the first matching place."""
    session = mock_open_meteo_session(PARIS_GEOCODING)

    with patch_session(session):
        result = await tool._geocode_location("Paris")

    assert result is not None
    assert result["name"] == "Paris"
    assert session.get.call_args[1]["params"]["name"] == "Paris"
    # Several candidates are needed to be able to prefer a nearby one.
    assert session.get.call_args[1]["params"]["count"] > 1


async def test_geocode_location_prefers_a_nearby_namesake(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a local suburb wins over a larger namesake far away."""
    # Home is in Perth, Western Australia.
    hass.config.latitude = -31.9523
    hass.config.longitude = 115.8613
    # Open-Meteo ranks by population, so the distant city comes back first.
    session = mock_open_meteo_session(
        {
            "results": [
                {
                    "name": "Richmond",
                    "latitude": 37.5407,
                    "longitude": -77.4360,
                    "country": "United States",
                    "timezone": "America/New_York",
                },
                {
                    "name": "Richmond",
                    "latitude": -32.0167,
                    "longitude": 115.9333,
                    "country": "Australia",
                    "admin1": "Western Australia",
                    "timezone": "Australia/Perth",
                },
            ],
        },
    )

    with patch_session(session):
        result = await tool._geocode_location("Richmond")

    assert result is not None
    assert result["country"] == "Australia"


async def test_geocode_location_keeps_ranking_when_nothing_is_nearby(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a distant place keeps Open-Meteo's own ordering."""
    # Home is in Perth, so nothing named Paris is anywhere close; the
    # top-ranked result must still win so travel lookups keep working.
    hass.config.latitude = -31.9523
    hass.config.longitude = 115.8613
    session = mock_open_meteo_session(
        {
            "results": [
                {
                    "name": "Paris",
                    "latitude": 48.85341,
                    "longitude": 2.3488,
                    "country": "France",
                    "timezone": "Europe/Paris",
                },
                {
                    "name": "Paris",
                    "latitude": 33.6609,
                    "longitude": -95.5555,
                    "country": "United States",
                    "timezone": "America/Chicago",
                },
            ],
        },
    )

    with patch_session(session):
        result = await tool._geocode_location("Paris")

    assert result is not None
    assert result["country"] == "France"


async def test_geocode_location_nearest_of_several_nearby(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that the closest match wins when several are nearby."""
    hass.config.latitude = -31.9523
    hass.config.longitude = 115.8613
    session = mock_open_meteo_session(
        {
            "results": [
                {"name": "Hamilton", "latitude": -32.5, "longitude": 115.9},
                {"name": "Hamilton", "latitude": -31.96, "longitude": 115.87},
            ],
        },
    )

    with patch_session(session):
        result = await tool._geocode_location("Hamilton")

    assert result is not None
    assert result["latitude"] == -31.96


async def test_geocode_location_ignores_candidates_without_coordinates(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a candidate missing coordinates cannot be selected as nearby."""
    hass.config.latitude = -31.9523
    hass.config.longitude = 115.8613
    session = mock_open_meteo_session(
        {
            "results": [
                {"name": "Somewhere", "country": "Australia"},
                {
                    "name": "Somewhere",
                    "latitude": -31.96,
                    "longitude": 115.87,
                    "country": "Australia",
                },
            ],
        },
    )

    with patch_session(session):
        result = await tool._geocode_location("Somewhere")

    assert result is not None
    assert result["latitude"] == -31.96


async def test_geocode_location_no_results(tool: WeatherForecastTool) -> None:
    """Test that a place name with no matches yields None."""
    with patch_session(mock_open_meteo_session({"results": []})):
        assert await tool._geocode_location("Nowhereville") is None


async def test_geocode_location_missing_results_key(
    tool: WeatherForecastTool,
) -> None:
    """Test that a response without a results key yields None."""
    with patch_session(mock_open_meteo_session({})):
        assert await tool._geocode_location("Nowhereville") is None


async def test_geocode_location_http_error(tool: WeatherForecastTool) -> None:
    """Test that a geocoding HTTP error yields None rather than raising."""
    session = mock_open_meteo_session(
        {},
        geocoding_status=HTTPStatus.SERVICE_UNAVAILABLE,
    )

    with patch_session(session):
        assert await tool._geocode_location("Paris") is None


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
def test_format_remote_daily_forecast(tool: WeatherForecastTool) -> None:
    """Test that daily location data matches the weather entity output style."""
    result = tool._format_remote_daily_forecast(
        DAILY_FORECAST,
        None,
        ZoneInfo("Europe/Paris"),
    )

    assert result == (
        "- Date: Today (Friday)\n"
        "  Temperature: 11 - 20\n"
        "  General Condition: cloudy\n"
        "  Chance of Precipitation: unlikely\n"
        "- Date: Saturday\n"
        "  Temperature: 14 - 24\n"
        "  General Condition: slight rain\n"
        "  Chance of Precipitation: very likely"
    )


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
def test_format_remote_daily_forecast_filters_target_date(
    tool: WeatherForecastTool,
) -> None:
    """Test that only the requested day is returned when one is given."""
    result = tool._format_remote_daily_forecast(
        DAILY_FORECAST,
        date(2026, 5, 2),
        ZoneInfo("Europe/Paris"),
    )

    assert "Saturday" in result
    assert "Friday" not in result


def test_format_remote_daily_forecast_without_low(
    tool: WeatherForecastTool,
) -> None:
    """Test that a day with no low temperature reports only the high."""
    data = {
        "daily": {
            "time": ["2026-05-01"],
            "temperature_2m_max": [20.4],
            "temperature_2m_min": [],
            "weather_code": [],
            "precipitation_probability_max": [],
        },
    }

    result = tool._format_remote_daily_forecast(data, None, None)

    assert "  Temperature: 20" in result
    # Nothing is reported for data the response did not include.
    assert "General Condition" not in result
    assert "Chance of Precipitation" not in result


def test_format_remote_daily_forecast_skips_days_without_temperature(
    tool: WeatherForecastTool,
) -> None:
    """Test that a day with no temperature at all is skipped."""
    data = {
        "daily": {
            "time": ["2026-05-01"],
            "temperature_2m_max": [],
        },
    }

    assert tool._format_remote_daily_forecast(data, None, None) == ""


def test_format_remote_daily_forecast_empty(tool: WeatherForecastTool) -> None:
    """Test that a response with no daily data yields an empty string."""
    assert tool._format_remote_daily_forecast({}, None, None) == ""


@pytest.mark.freeze_time("2026-05-01T05:00:00+00:00")
def test_format_remote_hourly_forecast(tool: WeatherForecastTool) -> None:
    """Test that hourly location data matches the weather entity output style."""
    # 07:00 in Paris, so both of that day's entries are still ahead.
    result = tool._format_remote_hourly_forecast(
        HOURLY_FORECAST,
        date(2026, 5, 1),
        ZoneInfo("Europe/Paris"),
    )

    assert result == (
        "- Time: 8am\n"
        "  Temperature: 12\n"
        "  General Condition: clear\n"
        "  Chance of Precipitation: none\n"
        "- Time: 9am\n"
        "  Temperature: 16\n"
        "  General Condition: partly cloudy\n"
        "  Chance of Precipitation: possible"
    )


@pytest.mark.freeze_time("2026-05-01T06:30:00+00:00")
def test_format_remote_hourly_forecast_drops_elapsed_hours(
    tool: WeatherForecastTool,
) -> None:
    """Test that hours already gone at the location are not reported."""
    # 08:30 in Paris: the 08:00 entry is the hour in progress and is kept,
    # while 09:00 is still ahead. Nothing earlier in the day is reported.
    data = {
        "hourly": {
            "time": [
                "2026-05-01T02:00",
                "2026-05-01T08:00",
                "2026-05-01T09:00",
            ],
            "temperature_2m": [5.0, 12.4, 15.6],
            "weather_code": [0, 0, 2],
            "precipitation_probability": [0, 0, 20],
        },
    }

    result = tool._format_remote_hourly_forecast(
        data,
        date(2026, 5, 1),
        ZoneInfo("Europe/Paris"),
    )

    assert "- Time: 2am" not in result
    assert "- Time: 8am" in result
    assert "- Time: 9am" in result


@pytest.mark.freeze_time("2026-05-01T21:30:00+00:00")
def test_format_remote_hourly_forecast_empty_once_day_has_passed(
    tool: WeatherForecastTool,
) -> None:
    """Test that a day whose hours have all gone reports nothing hourly."""
    # 23:30 in Paris, so the day's last hourly entry is behind us.
    result = tool._format_remote_hourly_forecast(
        HOURLY_FORECAST,
        date(2026, 5, 1),
        ZoneInfo("Europe/Paris"),
    )

    assert result == ""


@pytest.mark.freeze_time("2026-05-01T05:00:00+00:00")
def test_format_remote_hourly_forecast_skips_hours_without_temperature(
    tool: WeatherForecastTool,
) -> None:
    """Test that an hour with no temperature is skipped."""
    data = {"hourly": {"time": ["2026-05-01T08:00"], "temperature_2m": []}}

    result = tool._format_remote_hourly_forecast(
        data,
        None,
        ZoneInfo("Europe/Paris"),
    )

    assert result == ""


def test_format_remote_hourly_forecast_empty(tool: WeatherForecastTool) -> None:
    """Test that a response with no hourly data yields an empty string."""
    assert tool._format_remote_hourly_forecast({}, None) == ""


@pytest.mark.freeze_time("2026-05-01T05:00:00+00:00")
async def test_get_remote_forecast_requests_hourly_for_a_day(
    tool: WeatherForecastTool,
) -> None:
    """Test that a specific day requests hourly data, as entities do."""
    session = mock_open_meteo_session(PARIS_GEOCODING, HOURLY_FORECAST)

    with patch_session(session):
        result = await tool._get_remote_forecast(
            "Paris",
            "today",
            date(2026, 5, 1),
        )

    assert result is not None
    assert result.startswith("Weather for Paris, Ile-de-France, France:\n")
    assert "- Time: 8am" in result

    forecast_params = session.get.call_args_list[-1][1]["params"]
    assert "hourly" in forecast_params
    # Daily is requested alongside it, to fall back on once the day has gone.
    assert "daily" in forecast_params
    assert forecast_params["latitude"] == PARIS_GEOCODING["results"][0]["latitude"]
    assert forecast_params["timezone"] == "auto"


@pytest.mark.freeze_time("2026-05-01T21:30:00+00:00")
async def test_get_remote_forecast_falls_back_to_daily_once_day_has_passed(
    tool: WeatherForecastTool,
) -> None:
    """Test that a day with no hours left reports its daily summary instead."""
    # 23:30 in Paris. The entity path falls back to daily in this situation,
    # so a named location does the same rather than reporting nothing.
    session = mock_open_meteo_session(
        PARIS_GEOCODING,
        {**HOURLY_FORECAST, **DAILY_FORECAST},
    )

    with patch_session(session):
        result = await tool._get_remote_forecast(
            "Paris",
            "today",
            date(2026, 5, 1),
        )

    assert result is not None
    assert "- Time:" not in result
    assert "- Date: Today (Friday)" in result
    assert "  Temperature: 11 - 20" in result


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
async def test_get_remote_forecast_requests_daily_for_the_week(
    tool: WeatherForecastTool,
) -> None:
    """Test that the week ahead requests daily summaries, as entities do."""
    session = mock_open_meteo_session(PARIS_GEOCODING, DAILY_FORECAST)

    with patch_session(session):
        result = await tool._get_remote_forecast("Paris", "week", None)

    assert result is not None
    assert "- Date: Today (Friday)" in result

    forecast_params = session.get.call_args_list[-1][1]["params"]
    assert "daily" in forecast_params
    assert "hourly" not in forecast_params


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
async def test_get_remote_forecast_requests_configured_temperature_unit(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that the forecast is requested in Home Assistant's own unit."""
    session = mock_open_meteo_session(PARIS_GEOCODING, DAILY_FORECAST)

    with patch_session(session):
        await tool._get_remote_forecast("Paris", "week", None)
    assert session.get.call_args_list[-1][1]["params"]["temperature_unit"] == "celsius"

    hass.config.units = US_CUSTOMARY_SYSTEM
    session = mock_open_meteo_session(PARIS_GEOCODING, DAILY_FORECAST)

    with patch_session(session):
        await tool._get_remote_forecast("Paris", "week", None)
    assert (
        session.get.call_args_list[-1][1]["params"]["temperature_unit"] == "fahrenheit"
    )


@pytest.mark.freeze_time("2026-05-01T23:30:00-07:00")
async def test_get_remote_forecast_resolves_day_at_the_location(
    tool: WeatherForecastTool,
) -> None:
    """Test that the requested day is resolved against the location's clock."""
    # It is still 1 May here but already 2 May in Paris, so "today" in Paris
    # must select the Paris calendar day rather than the local one.
    session = mock_open_meteo_session(PARIS_GEOCODING, HOURLY_FORECAST)

    with patch_session(session):
        result = await tool._get_remote_forecast("Paris", "today", date(2026, 5, 1))

    assert result is not None
    # The 2 May entry is the only one kept once the day is resolved in Paris.
    assert "- Time: 8am\n  Temperature: 9" in result


async def test_get_remote_forecast_unknown_location(
    tool: WeatherForecastTool,
) -> None:
    """Test that an unresolvable place name yields None."""
    with patch_session(mock_open_meteo_session({"results": []})):
        assert await tool._get_remote_forecast("Nowhereville", "week", None) is None


async def test_get_remote_forecast_place_without_coordinates(
    tool: WeatherForecastTool,
) -> None:
    """Test that a geocoded place lacking coordinates yields None."""
    session = mock_open_meteo_session({"results": [{"name": "Paris"}]})

    with patch_session(session):
        assert await tool._get_remote_forecast("Paris", "week", None) is None


async def test_get_remote_forecast_http_error(tool: WeatherForecastTool) -> None:
    """Test that a forecast HTTP error raises ForecastRetrievalError."""
    session = mock_open_meteo_session(
        PARIS_GEOCODING,
        forecast_status=HTTPStatus.SERVICE_UNAVAILABLE,
    )

    with patch_session(session), pytest.raises(ForecastRetrievalError):
        await tool._get_remote_forecast("Paris", "week", None)


async def test_get_remote_forecast_empty_forecast(
    tool: WeatherForecastTool,
) -> None:
    """Test that a response containing no usable forecast yields None."""
    session = mock_open_meteo_session(PARIS_GEOCODING, {"daily": {"time": []}})

    with patch_session(session):
        assert await tool._get_remote_forecast("Paris", "week", None) is None


# =============================================================================
# async_call() location tests
# =============================================================================


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
async def test_async_call_with_location(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a location argument is served by Open-Meteo."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week", "location": "Paris"},
        tool_name="get_weather_forecast",
    )
    session = mock_open_meteo_session(PARIS_GEOCODING, DAILY_FORECAST)

    with patch_session(session):
        result = await tool.async_call(
            hass,
            tool_input,
            MagicMock(spec=llm.LLMContext),
        )

    assert isinstance(result, ToolResult)
    assert result.data["result"].startswith(
        "Weather for Paris, Ile-de-France, France:",
    )
    assert "  Temperature: 11 - 20" in result.data["result"]


async def test_async_call_with_location_not_found(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that an unresolvable location reports an error to the LLM."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week", "location": "Nowhereville"},
        tool_name="get_weather_forecast",
    )

    with patch_session(mock_open_meteo_session({"results": []})):
        result = await tool.async_call(
            hass,
            tool_input,
            MagicMock(spec=llm.LLMContext),
        )

    assert isinstance(result, ToolResult)
    assert result.error
    assert result.data == {
        "error": "Could not find weather data for 'Nowhereville'",
    }


async def test_async_call_location_does_not_use_weather_entities(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a location request never calls the local weather entities."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week", "location": "Paris"},
        tool_name="get_weather_forecast",
    )
    tool.config = {
        "weather_daily_entity": "weather.home",
        "weather_hourly_entity": "weather.home_hourly",
    }
    session = mock_open_meteo_session(PARIS_GEOCODING, DAILY_FORECAST)

    with (
        patch_session(session),
        patch.object(tool, "_get_daily_forecast", AsyncMock()) as mock_daily,
        patch.object(tool, "_get_hourly_forecast", AsyncMock()) as mock_hourly,
    ):
        result = await tool.async_call(
            hass,
            tool_input,
            MagicMock(spec=llm.LLMContext),
        )

    assert isinstance(result, ToolResult)
    mock_daily.assert_not_called()
    mock_hourly.assert_not_called()


async def test_async_call_location_error_is_reported(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a forecast failure for a location is reported to the LLM."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week", "location": "Paris"},
        tool_name="get_weather_forecast",
    )
    session = mock_open_meteo_session(
        PARIS_GEOCODING,
        forecast_status=HTTPStatus.SERVICE_UNAVAILABLE,
    )

    with patch_session(session):
        result = await tool.async_call(
            hass,
            tool_input,
            MagicMock(spec=llm.LLMContext),
        )

    assert isinstance(result, ToolResult)
    assert result.error
    assert "Failed to retrieve forecast" in result.data["error"]


# =============================================================================
# Requested temperature unit tests
# =============================================================================


@pytest.mark.parametrize(
    ("value", "source_unit", "requested_unit", "expected"),
    [
        # Without a requested unit the value is reported exactly as it arrived.
        (20.4, UnitOfTemperature.CELSIUS, None, 20),
        (20.6, UnitOfTemperature.CELSIUS, None, 21),
        ("20.4", UnitOfTemperature.CELSIUS, None, 20),
        (20, None, None, 20),
        # A requested unit is labelled, and converted only when it differs.
        (20, UnitOfTemperature.CELSIUS, UnitOfTemperature.CELSIUS, "20°C"),
        (20, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT, "68°F"),
        (68, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS, "20°C"),
        ("20", UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT, "68°F"),
        # An unknown source unit is assumed to already be in the target.
        (20, None, UnitOfTemperature.CELSIUS, "20°C"),
        (None, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT, None),
        (None, UnitOfTemperature.CELSIUS, None, None),
    ],
)
def test_format_temperature(
    value: Any,
    source_unit: str | None,
    requested_unit: str | None,
    expected: Any,
) -> None:
    """Test that temperatures convert and label only when a unit is asked for."""
    assert _format_temperature(value, source_unit, requested_unit) == expected


@pytest.mark.parametrize(
    ("high", "low", "requested_unit", "expected"),
    [
        (20, 15, None, "15 - 20"),
        (20, None, None, 20),
        (20, 15, UnitOfTemperature.CELSIUS, "15°C - 20°C"),
        (20, 15, UnitOfTemperature.FAHRENHEIT, "59°F - 68°F"),
        (20, None, UnitOfTemperature.FAHRENHEIT, "68°F"),
        (None, None, None, None),
    ],
)
def test_format_temperature_range(
    high: Any,
    low: Any,
    requested_unit: str | None,
    expected: Any,
) -> None:
    """Test that a high and low pair converts and labels as a pair."""
    result = _format_temperature_range(
        high,
        low,
        UnitOfTemperature.CELSIUS,
        requested_unit,
    )
    assert result == expected


def test_entity_temperature_unit(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that the unit a weather entity reports in is read from its state."""
    hass.states.async_set(
        "weather.home",
        "sunny",
        {"temperature_unit": UnitOfTemperature.FAHRENHEIT},
    )

    assert tool._entity_temperature_unit("weather.home") == (
        UnitOfTemperature.FAHRENHEIT
    )


def test_entity_temperature_unit_missing_entity(
    tool: WeatherForecastTool,
) -> None:
    """Test that an absent entity reports no unit."""
    assert tool._entity_temperature_unit("weather.nonexistent") is None


async def test_get_daily_forecast_converts_to_requested_unit(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a requested unit converts the local daily forecast."""
    hass.states.async_set(
        "weather.home",
        "sunny",
        {"temperature_unit": UnitOfTemperature.CELSIUS},
    )
    forecast_data = [
        {
            "datetime": "2026-05-01T00:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "condition": "Sunny",
        },
    ]
    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(
        return_value={"weather.home": {"forecast": forecast_data}},
    )
    tool.hass.services = mock_services

    result = await tool._get_daily_forecast(
        hass,
        "weather.home",
        None,
        UnitOfTemperature.FAHRENHEIT,
    )

    assert "  Temperature: 59°F - 68°F" in result


async def test_get_hourly_forecast_converts_to_requested_unit(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a requested unit converts the local hourly forecast."""
    hass.states.async_set(
        "weather.home",
        "sunny",
        {"temperature_unit": UnitOfTemperature.CELSIUS},
    )
    forecast_data = [
        {"datetime": "2026-05-01T08:00:00+00:00", "temperature": 20},
    ]
    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(
        return_value={"weather.home": {"forecast": forecast_data}},
    )
    tool.hass.services = mock_services

    with patch.object(
        WeatherForecastTool,
        "_filter_forecast_by_day",
        return_value=forecast_data,
    ):
        result = await tool._get_hourly_forecast(
            hass,
            "weather.home",
            date(2026, 5, 1),
            UnitOfTemperature.FAHRENHEIT,
        )

    assert "  Temperature: 68°F" in result


async def test_get_twice_daily_forecast_converts_to_requested_unit(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that a requested unit converts the local twice-daily forecast."""
    hass.states.async_set(
        "weather.home",
        "sunny",
        {"temperature_unit": UnitOfTemperature.CELSIUS},
    )
    forecast_data = [
        {
            "datetime": "2026-05-01T00:00:00+00:00",
            "temperature": 20,
            "templow": 15,
            "is_daytime": True,
        },
    ]
    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(
        return_value={"weather.home": {"forecast": forecast_data}},
    )
    tool.hass.services = mock_services

    result = await tool._get_twice_daily_forecast(
        hass,
        "weather.home",
        None,
        UnitOfTemperature.FAHRENHEIT,
    )

    assert "  Temperature: 59°F - 68°F" in result


def test_current_temperature_sensor_converts_to_requested_unit(
    hass: HomeAssistant,
) -> None:
    """Test that a requested unit converts the current temperature sensor."""
    hass.states.async_set(
        "sensor.outside",
        "20",
        {"unit_of_measurement": UnitOfTemperature.CELSIUS},
    )

    result = WeatherForecastTool._get_current_temperature_sensor_data(
        hass,
        "sensor.outside",
        UnitOfTemperature.FAHRENHEIT,
    )

    assert result == "- Time: current\n  Temperature: 68°F"


def test_current_temperature_sensor_without_requested_unit(
    hass: HomeAssistant,
) -> None:
    """Test that the sensor is reported unconverted when no unit is asked for."""
    hass.states.async_set(
        "sensor.outside",
        "20",
        {"unit_of_measurement": UnitOfTemperature.CELSIUS},
    )

    result = WeatherForecastTool._get_current_temperature_sensor_data(
        hass,
        "sensor.outside",
    )

    assert result == "- Time: current\n  Temperature: 20"


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
@pytest.mark.parametrize(
    ("requested_unit", "expected_param"),
    [
        (UnitOfTemperature.CELSIUS, "celsius"),
        (UnitOfTemperature.FAHRENHEIT, "fahrenheit"),
    ],
)
async def test_get_remote_forecast_requests_the_asked_for_unit(
    tool: WeatherForecastTool,
    requested_unit: str,
    expected_param: str,
) -> None:
    """Test that a requested unit is what Open-Meteo is asked to return."""
    session = mock_open_meteo_session(PARIS_GEOCODING, DAILY_FORECAST)

    with patch_session(session):
        result = await tool._get_remote_forecast(
            "Paris",
            "week",
            None,
            requested_unit,
        )

    params = session.get.call_args_list[-1][1]["params"]
    assert params["temperature_unit"] == expected_param
    # Values arrive in the requested unit, so they are labelled but not converted.
    assert result is not None
    assert f"  Temperature: 11{requested_unit} - 20{requested_unit}" in result


@pytest.mark.freeze_time("2026-05-01T12:00:00+00:00")
async def test_async_call_with_requested_unit_for_location(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that the unit argument reaches the Open-Meteo request."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week", "location": "Paris", "unit": "fahrenheit"},
        tool_name="get_weather_forecast",
    )
    session = mock_open_meteo_session(PARIS_GEOCODING, DAILY_FORECAST)

    with patch_session(session):
        result = await tool.async_call(
            hass,
            tool_input,
            MagicMock(spec=llm.LLMContext),
        )

    assert session.get.call_args_list[-1][1]["params"]["temperature_unit"] == (
        "fahrenheit"
    )
    assert isinstance(result, ToolResult)
    assert "  Temperature: 11°F - 20°F" in result.data["result"]


async def test_async_call_with_requested_unit_for_local_weather(
    tool: WeatherForecastTool,
    hass: HomeAssistant,
) -> None:
    """Test that the unit argument converts the local weather forecast."""
    tool_input = llm.ToolInput(
        tool_args={"range": "week", "unit": "fahrenheit"},
        tool_name="get_weather_forecast",
    )
    tool.config = {"weather_daily_entity": "weather.home"}
    hass.states.async_set(
        "weather.home",
        "sunny",
        {"temperature_unit": UnitOfTemperature.CELSIUS, "supported_features": 0},
    )
    forecast_data = [
        {
            "datetime": "2026-05-01T00:00:00+00:00",
            "temperature": 20,
            "templow": 15,
        },
    ]
    mock_services = MagicMock()
    mock_services.async_call = AsyncMock(
        return_value={"weather.home": {"forecast": forecast_data}},
    )
    tool.hass.services = mock_services

    result = await tool.async_call(
        hass,
        tool_input,
        MagicMock(spec=llm.LLMContext),
    )

    assert isinstance(result, ToolResult)
    assert "  Temperature: 59°F - 68°F" in result.data["result"]
