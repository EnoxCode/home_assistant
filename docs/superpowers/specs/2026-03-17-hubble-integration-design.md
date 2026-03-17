# Hubble Home Assistant Integration — Design Spec

**Date:** 2026-03-17
**Branch:** hubble-integration
**Scope:** Initial integration — config flow, one coordinator, one sensor (current page)

---

## Overview

A new Home Assistant integration for **Hubble**, a local kitchen dashboard application. Hubble exposes a RESTful API (OpenAPI 3.0) on `http://{host}:{port}`. This integration connects via HTTP polling using an API key, surfaces dashboard state as HA entities, and is designed to grow into a full-featured integration with switches, buttons, selects, and events.

---

## Files

```
homeassistant/components/hubble/
├── __init__.py         # async_setup_entry / async_unload_entry
├── manifest.json       # domain metadata, iot_class: local_polling
├── const.py            # DOMAIN, DEFAULT_PORT, SCAN_INTERVAL
├── api.py              # HubbleApiClient — thin HTTP layer + exceptions
├── coordinator.py      # HubbleCoordinator — DataUpdateCoordinator
├── config_flow.py      # HubbleConfigFlow — user + reauth steps
├── sensor.py           # HubbleCurrentPageSensor
├── strings.json        # UI strings for config flow and entities
└── icons.json          # Entity icons

tests/components/hubble/
├── __init__.py
├── conftest.py
├── test_config_flow.py
└── test_sensor.py
```

---

## Config Flow (`config_flow.py`)

```python
class HubbleConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
```

### Step: `async_step_user`

Form fields:
| Field | Key | Type | Default |
|---|---|---|---|
| Host | `CONF_HOST` | `str` | — |
| Port | `CONF_PORT` | `int` | `3000` |
| API Key | `CONF_API_KEY` | `str` | — |

(`CONF_HOST`, `CONF_PORT`, `CONF_API_KEY` all imported from `homeassistant.const`)

Validation: creates a `HubbleApiClient` and calls `async_get_state()`. This is the same method the coordinator uses — no separate `async_validate_connection` alias.

Error mapping:
- `HubbleAuthError` → `errors["base"] = "invalid_auth"`
- `HubbleConnectionError` → `errors["base"] = "cannot_connect"`
- `Exception` (unexpected) → logs the error, `errors["base"] = "unknown"`

Same error mapping applies in `async_step_reauth_confirm`.

Duplicate prevention: `_async_abort_entries_match({CONF_HOST: ..., CONF_PORT: ...})`

On success: creates entry titled `"Hubble ({host}:{port})"`.

### Re-auth: `async_step_reauth` → `async_step_reauth_confirm`

`async_step_reauth` delegates immediately to `async_step_reauth_confirm` (HA convention — step ID must match `strings.json`).

`async_step_reauth_confirm` shows a single API Key field (host/port pre-filled from existing entry). On success, updates the entry and reloads it.

---

## API Client (`api.py`)

Class: `HubbleApiClient`

```python
HubbleApiClient(host: str, port: int, api_key: str, session: aiohttp.ClientSession)
```

Base URL: `http://{host}:{port}`
Auth header: `x-api-key: {api_key}` on every request.

### Methods (initial)

| Method | Endpoint | Used by |
|---|---|---|
| `async_get_state()` | `GET /api/dashboard/state` | coordinator + config flow validation |

Config flow calls `async_get_state()` directly — no separate `async_validate_connection` alias.

### Exceptions

```python
class HubbleError(HomeAssistantError): ...
class HubbleAuthError(HubbleError): ...       # HTTP 401
class HubbleConnectionError(HubbleError): ... # network / timeout
```

---

## Coordinator (`coordinator.py`)

Class: `HubbleCoordinator(DataUpdateCoordinator[dict[str, Any]])`

Type alias: `type HubbleConfigEntry = ConfigEntry[HubbleCoordinator]`

- **Poll endpoint:** `GET /api/dashboard/state`
- **Poll interval:** 30 seconds
- **Data shape:**
```json
{
  "activePage": 1,
  "screenOn": true,
  "pages": [...],
  "widgets": [...],
  "templateId": "standard",
  "selectedWidgetId": null
}
```

Error handling in `_async_update_data`:
- `HubbleAuthError` → raises `ConfigEntryAuthFailed` (triggers re-auth flow)
- `HubbleConnectionError` → raises `UpdateFailed` (entities go unavailable)

`async_config_entry_first_refresh()` automatically converts `UpdateFailed` into `ConfigEntryNotReady`, so `__init__.py` needs no explicit try/except around first refresh — HA handles the retry scheduling.

`config_entry.runtime_data` holds the coordinator instance.

---

## Sensor Platform (`sensor.py`)

### `HubbleCurrentPageSensor`

Extends `CoordinatorEntity[HubbleCoordinator]` and `SensorEntity`.

| Property | Value |
|---|---|
| `_attr_has_entity_name` | `True` |
| `translation_key` | `"current_page"` |
| `unique_id` | `{entry_id}_current_page` |
| `native_value` | page `name` from `pages` list matching `activePage` id |
| `extra_state_attributes` | `{"slug": ..., "id": ...}` |
| `device_class` | `None` |

**Icon:** declared in `icons.json` under `entity.sensor.current_page.default = "mdi:book-open-page-variant"` — not set as a Python property.

**`available` property:** overridden as `return super().available and coordinator.data is not None and <active page found in pages>`. Chains the base class `last_update_success` guard with the Hubble-specific data checks, so the entity shows as *unavailable* (not *unknown*) when data is missing or the active page cannot be resolved.

**Device:** all entities attach a shared `DeviceInfo`:
```python
DeviceInfo(
    identifiers={(DOMAIN, entry.entry_id)},
    name=f"Hubble ({entry.data[CONF_HOST]}:{entry.data[CONF_PORT]})",
    manufacturer="Hubble",
)
```

---

## `__init__.py`

```python
PLATFORMS = [Platform.SENSOR]

async def async_setup_entry(hass, entry) -> bool:
    session = async_get_clientsession(hass)
    client = HubbleApiClient(
        entry.data[CONF_HOST], entry.data[CONF_PORT],
        entry.data[CONF_API_KEY], session
    )
    coordinator = HubbleCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    # UpdateFailed from _async_update_data is automatically converted to
    # ConfigEntryNotReady by async_config_entry_first_refresh — no try/except needed.
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, entry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

---

## `manifest.json`

```json
{
  "domain": "hubble",
  "name": "Hubble",
  "codeowners": [],
  "config_flow": true,
  "documentation": "",
  "integration_type": "hub",
  "iot_class": "local_polling",
  "requirements": []
}
```

No third-party Python library — uses HA's built-in `aiohttp` session.

---

## `const.py`

```python
from datetime import timedelta

DOMAIN = "hubble"
DEFAULT_PORT = 3000
SCAN_INTERVAL = timedelta(seconds=30)
```

`CONF_HOST`, `CONF_PORT`, `CONF_API_KEY` are imported from `homeassistant.const` everywhere — not redefined here.

---

## `strings.json`

```json
{
  "config": {
    "step": {
      "user": {
        "data": {
          "host": "Host",
          "port": "Port",
          "api_key": "API Key"
        }
      },
      "reauth_confirm": {
        "data": {
          "api_key": "API Key"
        }
      }
    },
    "error": {
      "cannot_connect": "Cannot connect to Hubble",
      "invalid_auth": "Invalid API key",
      "unknown": "Unexpected error"
    },
    "abort": {
      "already_configured": "This Hubble instance is already configured",
      "reauth_successful": "Re-authentication successful"
    }
  },
  "entity": {
    "sensor": {
      "current_page": {
        "name": "Current Page"
      }
    }
  }
}
```

---

## `icons.json`

```json
{
  "entity": {
    "sensor": {
      "current_page": {
        "default": "mdi:book-open-page-variant"
      }
    }
  }
}
```

---

## Testing

### `test_config_flow.py`
- Happy path: valid credentials → entry created with correct title
- `HubbleAuthError` → shows `invalid_auth` error, form re-rendered
- `HubbleConnectionError` → shows `cannot_connect` error, form re-rendered
- Duplicate host+port → aborted with `already_configured`
- Re-auth: new API key accepted → entry updated and reloaded

### `test_sensor.py`
- Sensor state matches page name from coordinator data
- Sensor `available = False` when coordinator data is `None`
- Sensor `available = False` when `activePage` not found in `pages`
- `extra_state_attributes` contains correct `slug` and `id`

Mocks: `HubbleApiClient.async_get_state` patched in all tests.

---

## Future Extensions (out of scope for this spec)

The architecture is designed to accommodate:
- `binary_sensor`: screen on/off (`data["screenOn"]`)
- `switch`: screen on/off (actionable via `POST /api/dashboard/screen`)
- `button`: next page, previous page, refresh dashboard
- `select`: active page (choose from `data["pages"]`)
- `notify` service: `POST /api/dashboard/notify`
- `event`: page changed (via polling diff)

All future entities attach the same `DeviceInfo` so they are grouped under one device in the UI.
