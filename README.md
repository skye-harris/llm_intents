# Tools for Assist _(Custom Integration for Home Assistant)_

Additional tools for LLM-backed Assist for Home Assistant:

* **Web Search** powered by your choice of _Brave_ or _SearXNG_
* **Location Search** powered by Google Places
* **Wikipedia**
* **Weather Forecast**
* **YouTube Search and Playback**

Each tool is optional and configurable via the integrations UI. Some tools require API keys, but are usable on free tiers.
A caching layer is utilised in order to reduce both API usage and latency on repeated requests for the same information within a 2-hour period.

---

## Installation

### Install via HACS (recommended)

Have [HACS](https://hacs.xyz/) installed, this will allow you to update easily.

* Adding Tools for Assist to HACS can be using this button:
  [![image](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=skye-harris&repository=llm_intents&category=integration)

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

* Requires a [Brave Search API key](https://brave.com/search/api/).
  * Brave provide $5 of free credit per month, equal to 1000 searches.

#### Configuration Steps

1. Select "Brave" as the search provider during setup.
2. Enter your [Brave "Data for AI" API key](https://api-dashboard.search.brave.com/app/subscriptions/subscribe?tab=ai).
3. Configure optional settings like number of results, location preferences.

#### Options

| Setting             | Required | Default | Description                                                 |
|---------------------|----------|---------|-------------------------------------------------------------|
| `API Key`           | ✅        | —       | Brave Search API key                                        |
| `Number of Results` | ✅        | `2`     | Number of results to provide to the LLM                     |
| `Country Code`      | ❌        | —       | ISO country code to bias results                            |
| `Latitude`          | ❌        | —       | Optional latitude for local result relevance (recommended)  |
| `Longitude`         | ❌        | —       | Optional longitude for local result relevance (recommended) |
| `Timezone`          | ❌        | —       | Optional TZ timezone identifier for local result relevance  |
| `Post Code`         | ❌        | —       | Optional post code for local result relevance               |

---

### 🔍 SearXNG Web Search

Uses a self-hosted SearXNG search service to return summarized results.

##### Requirements

* Requires a SearXNG server instance, with JSON responses enabled (https://github.com/searxng/searxng-docker).

#### Configuration Steps

1. Select "SearXNG" as the search provider during setup.
2. Configure your server URL and maximum search results to provide to the LLM.
   1. Server should be in the format: `protocol://host:port`, eg: `http://192.168.0.1:8080` 

#### Options

| Setting             | Required | Default | Description                             |
|---------------------|----------|---------|-----------------------------------------|
| `Number of Results` | ✅        | `2`     | Number of results to provide to the LLM |

---

### 📍 Google Places

Searches for locations, businesses, or points of interest using the Google Places API.

Search results include the location name, address, rating score, current open state, and when it next opens/closes.

#### Requirements

* Requires a [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/overview).
* Ensure the Places API is enabled in your Google Cloud project.

#### Configuration Steps

1. Select "Google Places" during setup.
2. Enter your [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/overview).
3. Configure number of results to return.

#### Options

| Setting             | Required | Default    | Description                                                                 |
|---------------------|----------|------------|-----------------------------------------------------------------------------|
| `API Key`           | ✅        | —          | Google Places API key                                                       |
| `Number of Results` | ✅        | `2`        | Number of location results to return                                        |
| `Latitude`          | ❌        | —          | Your locations latitude, if you wish to use location biasing (recommended)  |
| `Longitude`         | ❌        | —          | Your locations longitude, if you wish to use location biasing (recommended) |
| `Radius`            | ❌        | `5`        | The radius around your location for location biased results (in kilometres) |
| `Rank Preference`   | ❌        | `Distance` | The ranking preference for search results from Google Places                |

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

At a minimum, this tool requires a weather entity that provides either daily or twice-daily forecast data.
It is recommended, though optional, to also specify a weather entity that provides hourly weather data.

For cases where a specific days weather is requested (eg: `today`, `tomorrow`, `wednesday`), the hourly data will be provided if available.
If data for the week is requested, no hourly forecast entity is set, or the hourly forecast does not contain data for the requested day, the daily weather data will be used instead.

#### Requirements

* An existing weather forecast integration configured within Home Assistant.

#### Configuration Steps

1. Select "Weather Forecast" during setup.
2. Select the weather entity that provides daily forecast information.
3. Optionally, select the weather entity that provides hourly forecast information.
4. Optionally, select a local temperature sensor entity to display current temperature for today's hourly forecast.

### Options

| Setting                      | Required | Description                                                                                                 |
|------------------------------|----------|-------------------------------------------------------------------------------------------------------------|
| `Daily Weather Entity`       | ✅        | The weather entity to use for daily weather forecast data                                                   |
| `Hourly Weather Entity`      | ❌        | The weather entity to use for hourly weather forecast data                                                  |
| `Current Temperature Sensor` | ❌        | Optional local sensor entity to provide current temperature when requesting today's hourly weather forecast |

### 🎥 YouTube Search + Playback

Searches YouTube for videos and enables playback on compatible media players. The tool combines YouTube search capabilities with intelligent media player detection to provide a seamless video playback experience.

Search results include video titles, URLs, channel names, descriptions, and publication dates. When a user requests to play a video, the search results are automatically used with the playback tool to start video on the appropriate device.

#### Requirements

* Requires a [Google API key](https://console.cloud.google.com/apis/credentials) with the **YouTube Data API v3** enabled.
* The same Google API key can be shared with the Google Places tool if both are configured.
* Google provides a free tier with generous quotas for YouTube Data API v3.

#### Configuration Steps

1. Select "YouTube" during setup.
2. Enter your Google API key (the same key used for Google Places if configured).
3. Configure the number of search results to return (default: 1).

#### Playback Compatibility

The YouTube tool works seamlessly with Home Assistant media players that support video playback. Video-capable devices are automatically detected based on their `device_class` attribute:

**Supported Device Classes:**
* `tv` - Television devices (e.g., smart TVs, Android TV boxes)
* `receiver` - AV receivers with video output

**Not Supported:**
* `speaker` - Audio-only devices are automatically excluded
* Media players without a `device_class` set - These must be explicitly configured

**Playback Targeting:**
Videos can be played by specifying:
* **Entity ID** - Direct entity selection (e.g., `media_player.living_room_tv`)
* **Area** - Play on all video-capable devices in an area (e.g., "Living Room")
* **Device ID** - Target a specific device by its device registry ID

The tool automatically filters media players to only include video-capable devices when using area-based targeting, ensuring videos are only sent to devices that can display them.

#### How It Works

1. **Search**: When a user requests a YouTube video, the `search_youtube` tool queries YouTube's API and returns matching videos with metadata.
2. **Playback**: If the user wants to play a video, the `play_video` tool uses the video URL from search results and calls Home Assistant's `media_player.play_media` service on the target device(s).
3. **Caching**: Search results are cached for 2 hours to reduce API usage and improve response times for repeated queries.

#### Options

| Setting             | Required | Default | Description                                                           |
|---------------------|----------|---------|-----------------------------------------------------------------------|
| `API Key`           | ✅        | —       | Google API key with YouTube Data API v3 enabled                      |
| `Number of Results` | ✅        | `1`     | Number of video results to return (1-25). Use more for multiple options. |

---

## Acknowledgements

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

---

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/skyeharris)
