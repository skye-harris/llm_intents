# Tools for Assist _(Custom Integration for Home Assistant)_

Additional tools for LLM-backed Assist for Home Assistant:

* **Brave Web Search**
* **Google Places**
* **Wikipedia**
* **Weather Forecast**

Each tool is optional and configurable via the integrations UI. Some tools require API keys, but are usable on free tiers.
A caching layer is utilised in order to reduce both API usage and latency on repeated requests for the same information within a 12-hour period.

---

## Installation

### Install via HACS (recommended)

Have [HACS](https://hacs.xyz/) installed, this will allow you to update easily.

* Adding Tools for Assist to HACS can be using this button:
  [![image](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=skye-harris&repository=llm-intents&category=integration)

<br>

> [!NOTE]
> If the button above doesn't work, add `https://github.com/skye-harris/llm_intents` as a custom repository of type Integration in HACS.

* Click install on the `Tools for Assist` integration.
* Restart Home Assistant.

<details><summary>Manual Install</summary>

* Copy the `llm-intents`  folder from [latest release](https://github.com/skye-harris/llm_intents/releases/latest) to the [
  `custom_components` folder](https://developers.home-assistant.io/docs/creating_integration_file_structure/#where-home-assistant-looks-for-integrations) in your config directory.
* Restart the Home Assistant.

</details>

## Integration Configuration

After installation, configure the integration through Home Assistant's UI:

1. Go to `Settings` → `Devices & Services`.
2. Click `Add Integration`.
3. Search for `Tools for Assist`.
4. Follow the setup wizard to configure your desired services.

## Conversation Agent Configuration 

Once the integration is installed and configured, you will need to enable the desired services within your Conversation Agent entities.

For the Ollama and OpenAI Conversation integrations, this can be found within your Conversation Agent configuration options, beneath
the `Control Home Assistant` heading, and enabling the services desired for the Agent:
- Search Services
- Weather Forecast

### 🔍 Brave Web Search

Uses the Brave Web Search API to return summarized, snippet-rich results.

##### Requirements

* Requires a [Brave "Data for AI" API key](https://api-dashboard.search.brave.com/app/subscriptions/subscribe?tab=ai).
* The free tier plan is supported.

#### Configuration Steps

1. Select "Brave Search" during setup.
2. Enter your [Brave "Data for AI" API key](https://api-dashboard.search.brave.com/app/subscriptions/subscribe?tab=ai).
3. Configure optional settings like number of results, location preferences.

#### Options

| Setting             | Required | Default | Description                                   |
|---------------------|----------|---------|-----------------------------------------------|
| `API Key`           | ✅        | —       | Brave Search API key                          |
| `Number of Results` | ✅        | `2`     | Number of results to return                   |
| `Country Code`      | ❌        | —       | ISO country code to bias results              |
| `Latitude`          | ❌        | —       | Optional latitude for local result relevance  |
| `Longitude`         | ❌        | —       | Optional longitude for local result relevance |
| `Timezone`          | ❌        | —       | Optional timezone for local result relevance  |
| `Post Code`         | ❌        | —       | Optional post code for local result relevance |

---

### 📍 Google Places

Searches for locations, businesses, or points of interest using the Google Places API.

#### Requirements

* Requires a [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/overview).
* Ensure the Places API is enabled in your Google Cloud project.

#### Configuration Steps

1. Select "Google Places" during setup.
2. Enter your [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/overview).
3. Configure number of results to return.

#### Options

| Setting             | Required | Default | Description                          |
|---------------------|----------|---------|--------------------------------------|
| `API Key`           | ✅        | —       | Google Places API key                |
| `Number of Results` | ✅        | `2`     | Number of location results to return |

---

### 📚 Wikipedia

Looks up Wikipedia articles and returns summaries of the top results.

#### Requirements

* No API key required.
* Uses the public Wikipedia search and summary APIs.

#### Configuration Steps

1. Select "Wikipedia" during setup.
2. Configure number of article summaries to return (no API key required).

### Options

| Setting             | Required | Default | Description                           |
|---------------------|----------|---------|---------------------------------------|
| `Number of Results` | ✅        | `1`     | Number of article summaries to return |

---

### ⛅ Weather Forecast

Rather than accessing the internet directly for weather information, this tool utilises your existing Home Assistant weather integration and makes the forecast data accessible to your LLM in an intelligent manner.

At a minimum, this tool requires a weather entity that provides daily forecast data.
It is recommended, though optional, to also specify a weather entity that provides hourly weather data.

For cases where a specific days weather is requested (eg: `today`, `tomorrow`, `wednesday`), the hourly data will be provided if available.
If data for the week is requested, no hourly forecast entity is set, or the hourly forecast does not contain data for the requested day, the daily weather data will be used instead.

#### Requirements

* An existing weather forecast integration configured within Home Assistant.

#### Configuration Steps

1. Select "Weather Forecast" during setup.
2. Select the weather entity that provides daily forecast information.
3. Optionally, select the weather entity that provides hourly forecast information.

### Options

| Setting                 | Required | Description                                                 |
|-------------------------|----------|-------------------------------------------------------------|
| `Daily Weather Entity`  | ✅        | The weather entity to use for daily weather forecast data   |
| `Hourly Weather Entity` | ❌        | The weather entity to use for hourly weather forecast d ata |

## Acknowledgements

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
