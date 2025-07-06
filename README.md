# LLM Intents (Custom Integration for Home Assistant)

Additional tool intents for LLM-backed Assist for Home Assistant

Supported search sources:

* **Brave Search**
* **Google Places**
* **Wikipedia**

Each intent is optional and configurable via YAML. Some require API keys, but are usable on free tiers.

---

## Installation

1. Copy this repo into `/config/custom_components/llm_intents/` of your Home Assistant installation.
2. Add configuration to `/config/configuration.yaml`.
3. Restart Home Assistant.


## 🔍 Brave Search

Uses the Brave AI Web Search API to return summarized, snippet-rich results.

### Requirements

* Requires a [Brave "Data for AI" API key](https://api-dashboard.search.brave.com/app/subscriptions/subscribe?tab=ai)
* The free tier plan is supported

### Example Configuration

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

### Options

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

## 📍 Google Places

Searches for locations, businesses, or points of interest using the Google Places API.

### Requirements

* Requires a [Google Places API key](https://developers.google.com/maps/documentation/places/web-service/overview)
* Ensure the Places API is enabled in your Google Cloud project.

### Example Configuration

```yaml
llm_intents:
  google_places:
    api_key: !secret google_api
    num_results: 3
```

### Options

| Key           | Required | Default | Description                          |
| ------------- | -------- | ------- | ------------------------------------ |
| `api_key`     | ✅        | —       | Google Places API key                |
| `num_results` | ❌        | `2`     | Number of location results to return |

---

## 📚 Wikipedia

Looks up Wikipedia articles and returns summaries of the top results.

### Requirements

* No API key required.
* Uses the public Wikipedia search and summary APIs.

### Example Configuration

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
