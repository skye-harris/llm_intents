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

### 🔍 Brave Search

Uses the Brave AI Web Search API to return summarized, snippet-rich results.

##### Requirements

* Requires a [Brave "Data for AI" API key](https://api-dashboard.search.brave.com/app/subscriptions/subscribe?tab=ai)
* The free tier plan is supported

#### Example Configuration

```yaml
llm_intents:
  brave_search:
    api_key: !secret brave_ai_api
    num_results: 2
    country_code: "AU"
    latitude: -31.95
    longitude: 115.86
    timezone: "Australia/Perth"
    post_code: "6000"
```

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

#### Example Configuration

```yaml
llm_intents:
  google_places:
    api_key: !secret google_api
    num_results: 3
```

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

#### Example Configuration

```yaml
llm_intents:
  wikipedia: true

or

llm_intents:
  wikipedia:
    num_results: 1
```

### Options

| Key           | Required | Default | Description                           |
| ------------- | -------- | ------- | ------------------------------------- |
| `num_results` | ❌        | `1`     | Number of article summaries to return |

## Acknowledgements
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
