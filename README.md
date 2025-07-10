# LLM Intents (Custom Integration for Home Assistant)

Additional tool intents for LLM-backed Assist for Home Assistant

Supported search sources:

* **Brave Search**
* **Google Places**
* **Wikipedia**

Each intent is optional and configurable via YAML. Some require API keys, but are usable on free tiers.

TODOs:
- [ ] Add UI capabilities for configuration
- [ ] Implement proper error handling
- [ ] Code optimization/cleanup

---

## Installation

### Install via HACS (recommended)

Have [HACS](https://hacs.xyz/) installed, this will allow you to update easily.

* Adding LLM Intents to HACS can be using this button:
[![image](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=douskye-harris&repository=llm-intents&category=integration)

> [!NOTE]
> If the button above doesn't work, add `https://github.com/skye-harris/llm_intents` as a custom repository of type Integration in HACS.

* Click install on the `LLM Intents` integration.
* Restart Home Assistant.


<details><summary>Manual Install</summary>

* Copy the `llm-intents`  folder from [latest release](https://github.com/dougiteixeira/proxmoxve/releases/latest) to the [`custom_components` folder](https://developers.home-assistant.io/docs/creating_integration_file_structure/#where-home-assistant-looks-for-integrations) in your config directory.
* Restart the Home Assistant.
</details>

## Configuration

After installation, configure the integration through Home Assistant's UI:

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "LLM Intents"
4. Follow the setup wizard to configure your desired services

### 🔍 Brave Search

Uses the Brave AI Web Search API to return summarized, snippet-rich results.

##### Requirements

* Requires a [Brave "Data for AI" API key](https://api-dashboard.search.brave.com/app/subscriptions/subscribe?tab=ai)
* The free tier plan is supported

#### Configuration Steps

1. Select "Brave Search" during setup
2. Enter your [Brave "Data for AI" API key](https://api-dashboard.search.brave.com/app/subscriptions/subscribe?tab=ai)
3. Configure optional settings like number of results, location preferences

#### Options

| Key            | Required | Default | Description                                       |
| -------------- | -------- | ------- | ------------------------------------------------- |
| `api_key`      | ✅        | —       | Brave Search API key                              |
| `num_results`  | ❌        | `2`     | Number of results to return                       |
| `country_code` | ❌        | —       | ISO country code to bias results                  |
| `latitude`     | ❌        | —       | Optional latitude for local relevance             |
| `longitude`    | ❌        | —       | Optional longitude for local relevance            |
| `timezone`     | ❌        | —       | Timezone for contextual answers                   |
| `post_code`    | ❌        | —       | Optional postcode for more accurate geo targeting |

---

### 📍 Google Places

Searches for locations, businesses, or points of interest using the Google Places API.

#### Requirements

* Requires a [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/overview)
* Ensure the Places API is enabled in your Google Cloud project.

#### Configuration Steps

1. Select "Google Places" during setup  
2. Enter your [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/overview)
3. Configure number of results to return

#### Options

| Key           | Required | Default | Description                          |
| ------------- | -------- | ------- | ------------------------------------ |
| `api_key`     | ✅        | —       | Google Places API key                |
| `num_results` | ❌        | `2`     | Number of location results to return |

---

### 📚 Wikipedia

Looks up Wikipedia articles and returns summaries of the top results.

#### Requirements

* No API key required.
* Uses the public Wikipedia search and summary APIs.

#### Configuration Steps

1. Select "Wikipedia" during setup
2. Configure number of article summaries to return (no API key required)

### Options

| Key           | Required | Default | Description                           |
| ------------- | -------- | ------- | ------------------------------------- |
| `num_results` | ❌        | `1`     | Number of article summaries to return |

> [!IMPORTANT]
> **Security**: All API keys are stored securely in Home Assistant's encrypted configuration database, not in plain text files.

## Acknowledgements
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
