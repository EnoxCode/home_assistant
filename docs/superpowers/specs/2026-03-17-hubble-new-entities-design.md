# Hubble Integration: New Entities & Actions

**Date:** 2026-03-17
**Branch:** hubble-integration
**Status:** Approved (rev 2 — post spec review)

---

## Overview

Extend the Hubble Home Assistant integration with navigation buttons, a page selector, additional sensors, and two service actions for notification management. All new entities read from an extended single coordinator. Services are registered in `async_setup`.

---

## 1. Data Layer

### 1.1 Coordinator Extension

`HubbleCoordinator._async_update_data` is extended to call three endpoints in parallel:

```python
state, notify_count_resp, modules = await asyncio.gather(
    self.client.async_get_state(),
    self.client.async_get_notify_count(),
    self.client.async_get_modules(),
)
```

`asyncio.gather` uses default `return_exceptions=False` — the first exception propagates. Error handling in the coordinator wraps the entire gather:
- `HubbleAuthError` from any sub-call → raise `ConfigEntryAuthFailed`
- `HubbleConnectionError` from any sub-call → raise `UpdateFailed`

The returned dict merges all results, adding two new top-level keys:

| Key | Source | Type |
|---|---|---|
| `notificationCount` | `/api/dashboard/notify/count` → `.count` | `int` |
| `modules` | `/api/modules/` | `list[dict]` |

All existing keys (`activePage`, `screenOn`, `pages`, `widgets`, `templateId`, `selectedWidgetId`) remain unchanged.

### 1.2 New API Methods (`api.py`)

All new methods follow the existing error-handling pattern: catch `aiohttp.ClientError` → raise `HubbleConnectionError`; pass through `HubbleAuthError` on HTTP 401.

| Method | HTTP | Notes |
|---|---|---|
| `async_next_page()` | `POST /api/dashboard/next-page` | Returns page dict |
| `async_previous_page()` | `POST /api/dashboard/previous-page` | Returns page dict |
| `async_next_widget()` | `POST /api/dashboard/widget/next` | Returns `None` on HTTP 204 (no selectable widgets) |
| `async_previous_widget()` | `POST /api/dashboard/widget/previous` | Returns `None` on HTTP 204 |
| `async_set_active_page(page_id: int)` | `POST /api/dashboard/active-page` | Body: `{"pageId": page_id}` |
| `async_get_notify_count()` | `GET /api/dashboard/notify/count` | Returns `int` |
| `async_get_modules()` | `GET /api/modules/` | Returns `list[dict]` |
| `async_send_notification(title, message, **kwargs)` | `POST /api/dashboard/notify` | Returns `{"id": str, "success": bool}` |
| `async_dismiss_notification(notification_id: str)` | `DELETE /api/dashboard/notify/{id}` | |
| `async_dismiss_all_notifications()` | `DELETE /api/dashboard/notify` | |
| `async_refresh_dashboard()` | `POST /api/dashboard/refresh` | |

---

## 2. Entities

### 2.1 Buttons (`button.py`) — 6 new entities

All buttons are `CoordinatorEntity[HubbleCoordinator]` + `ButtonEntity`. After pressing, each calls `coordinator.async_request_refresh()` to update state immediately.

| Translation key | API method | Unique ID suffix |
|---|---|---|
| `next_page` | `async_next_page()` | `_next_page` |
| `previous_page` | `async_previous_page()` | `_previous_page` |
| `next_widget` | `async_next_widget()` | `_next_widget` |
| `previous_widget` | `async_previous_widget()` | `_previous_widget` |
| `dismiss_all_notifications` | `async_dismiss_all_notifications()` | `_dismiss_all_notifications` |
| `refresh_dashboard` | `async_refresh_dashboard()` | `_refresh_dashboard` |

All share the same `DeviceInfo` as the existing sensor (keyed on `(DOMAIN, entry.entry_id)`).

### 2.2 Page Selector (`select.py`) — 1 new entity

`HubblePageSelectEntity` is `CoordinatorEntity[HubbleCoordinator]` + `SelectEntity`.

**Option values use page slugs** (guaranteed unique by the Hubble API — duplicate slugs return HTTP 409). Page names are not used as option values to avoid ambiguity with duplicate names.

- **`options` property** — overridden as a plain `@property` (not `@cached_property`) returning `[page["slug"] for page in coordinator.data.get("pages", [])]`. The plain `@property` takes precedence over the parent's `@cached_property` via Python MRO.
- **`current_option`** — slug of the page whose `id` == `coordinator.data["activePage"]`; `None` if not found
- **`extra_state_attributes`** — `{"page_name": <current page name>}` so users can see the human-readable name alongside the slug state
- **On select:** finds the `page_id` matching the selected slug, calls `async_set_active_page(page_id)`, then `coordinator.async_request_refresh()`
- **Unique ID suffix:** `_active_page`
- **Translation key:** `active_page`

### 2.3 Sensors (`sensor.py`) — 2 new sensors

**`HubbleModuleCountSensor`**
- `native_value`: `len(coordinator.data.get("modules", []))`
- `state_class`: `SensorStateClass.MEASUREMENT`
- `native_unit_of_measurement`: `None` (dimensionless count — do not set a unit string for a raw count)
- `extra_state_attributes`: `{"modules": [m["name"] for m in modules]}`
- Translation key: `module_count`
- Unique ID suffix: `_module_count`

**`HubbleNotificationCountSensor`**
- `native_value`: `coordinator.data.get("notificationCount")`
- `state_class`: `SensorStateClass.MEASUREMENT`
- `native_unit_of_measurement`: `None` (dimensionless count)
- Translation key: `notification_count`
- Unique ID suffix: `_notification_count`

---

## 3. Service Actions

Registered in `async_setup` (not `async_setup_entry`) so they are always available for automation validation even with no loaded config entries.

`__init__.py` must also declare:
```python
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
```
This is required by `hassfest` whenever `async_setup` is present alongside `async_setup_entry`.

### 3.1 `hubble.send_notification`

Sends a notification overlay to a Hubble dashboard.

**Target level:** config entry (`config_entry_id` field using `ConfigEntrySelector({"integration": DOMAIN})`)

**Schema (voluptuous):**
```python
vol.Schema({
    vol.Required("config_entry_id"): selector.ConfigEntrySelector({"integration": DOMAIN}),
    vol.Required("title"): cv.string,
    vol.Required("message"): cv.string,
    vol.Optional("level", default="info"): vol.In(["info", "warning", "error", "critical"]),
    vol.Exclusive("permanent", "persistence_mode"): cv.boolean,
    vol.Exclusive("timer", "persistence_mode"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("image"): cv.string,
})
```

`vol.Exclusive` with group `"persistence_mode"` enforces that `permanent` and `timer` are mutually exclusive at schema validation time — no runtime checking needed.

**Fields (for `services.yaml`):**

| Field | Selector | Required |
|---|---|---|
| `config_entry_id` | `config_entry: {integration: hubble}` | yes |
| `title` | `text: {}` | yes |
| `message` | `text: {multiline: true}` | yes |
| `level` | `select: {options: [info, warning, error, critical], translation_key: notification_level}` | no |
| `permanent` | `boolean: {}` | no |
| `timer` | `number: {min: 1, mode: box}` | no |
| `image` | `text: {}` | no |

**Response:** `{"notification_id": "<uuid>"}` — captured via `response_variable` in automations.

Registered with `supports_response=SupportsResponse.OPTIONAL`. Handler checks `call.return_response` before returning data.

After a successful API call, triggers `coordinator.async_request_refresh()` so `notificationCount` updates immediately.

### 3.2 `hubble.dismiss_notification`

Dismisses a single active notification by ID.

**Target level:** config entry (`config_entry_id` field using `ConfigEntrySelector({"integration": DOMAIN})`)

**Schema:**
```python
vol.Schema({
    vol.Required("config_entry_id"): selector.ConfigEntrySelector({"integration": DOMAIN}),
    vol.Required("notification_id"): cv.string,
})
```

**Fields (for `services.yaml`):**

| Field | Selector | Required |
|---|---|---|
| `config_entry_id` | `config_entry: {integration: hubble}` | yes |
| `notification_id` | `text: {}` | yes |

No response data. Calls `async_dismiss_notification(notification_id)` then triggers `coordinator.async_request_refresh()`.

### 3.3 Service Handler Pattern

Both handlers follow this pattern:

```python
entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
if entry is None:
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="config_entry_not_found"
    )
if entry.state is not ConfigEntryState.LOADED:
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="config_entry_not_loaded"
    )
coordinator: HubbleCoordinator = entry.runtime_data
try:
    result = await coordinator.client.async_<method>(...)
except HubbleError as err:
    raise HomeAssistantError(str(err)) from err
await coordinator.async_request_refresh()
```

- `ServiceValidationError` for lookup/state failures (user-visible, no error traceback in logs)
- `HomeAssistantError` for API call failures (`HubbleError` subclasses)

---

## 4. Strings & Translations

### `strings.json` additions

Add top-level `"services"`, `"selector"`, and `"exceptions"` keys alongside the existing `"config"` and `"entity"` keys:

```json
{
  "services": {
    "send_notification": {
      "name": "Send notification",
      "description": "Sends a notification overlay to the Hubble dashboard.",
      "fields": {
        "config_entry_id": {"name": "Hubble instance", "description": "The Hubble dashboard to send the notification to."},
        "title": {"name": "Title", "description": "Short heading displayed at the top of the notification."},
        "message": {"name": "Message", "description": "Body text. Supports **bold**, *italic*, and `code` markdown."},
        "level": {"name": "Level", "description": "Severity level. Determines card colour and icon."},
        "permanent": {"name": "Permanent", "description": "If true, notification stays until dismissed."},
        "timer": {"name": "Timer", "description": "Seconds until auto-dismiss. Mutually exclusive with permanent."},
        "image": {"name": "Image", "description": "Optional image URL or base64 data URI."}
      }
    },
    "dismiss_notification": {
      "name": "Dismiss notification",
      "description": "Dismisses a single active notification by its ID.",
      "fields": {
        "config_entry_id": {"name": "Hubble instance", "description": "The Hubble dashboard to dismiss the notification on."},
        "notification_id": {"name": "Notification ID", "description": "UUID returned by the send_notification action."}
      }
    }
  },
  "selector": {
    "notification_level": {
      "options": {
        "info": "Info",
        "warning": "Warning",
        "error": "Error",
        "critical": "Critical"
      }
    }
  },
  "exceptions": {
    "config_entry_not_found": {"message": "Config entry not found."},
    "config_entry_not_loaded": {"message": "Hubble integration is not loaded."}
  }
}
```

Add new entity keys to the `"entity"` section:

```json
{
  "entity": {
    "button": {
      "next_page": {"name": "Next page"},
      "previous_page": {"name": "Previous page"},
      "next_widget": {"name": "Next widget"},
      "previous_widget": {"name": "Previous widget"},
      "dismiss_all_notifications": {"name": "Dismiss all notifications"},
      "refresh_dashboard": {"name": "Refresh dashboard"}
    },
    "select": {
      "active_page": {"name": "Active page"}
    },
    "sensor": {
      "current_page": {"name": "Current page"},
      "module_count": {"name": "Module count"},
      "notification_count": {"name": "Notification count"}
    }
  }
}
```

`translations/en.json` mirrors `strings.json` exactly.

---

## 5. `services.yaml`

Full structure (field selectors as described in section 3):

```yaml
send_notification:
  fields:
    config_entry_id:
      required: true
      selector:
        config_entry:
          integration: hubble
    title:
      required: true
      selector:
        text: {}
    message:
      required: true
      selector:
        text:
          multiline: true
    level:
      selector:
        select:
          translation_key: notification_level
          options:
            - info
            - warning
            - error
            - critical
    permanent:
      selector:
        boolean: {}
    timer:
      selector:
        number:
          min: 1
          mode: box
    image:
      selector:
        text: {}

dismiss_notification:
  fields:
    config_entry_id:
      required: true
      selector:
        config_entry:
          integration: hubble
    notification_id:
      required: true
      selector:
        text: {}
```

`config_entry_id` must appear in `services.yaml` so the HA UI renders a config entry picker for the field. Without it the field is invisible in the automation editor.

---

## 6. `icons.json` additions

```json
{
  "entity": {
    "button": {
      "next_page": {"default": "mdi:chevron-right"},
      "previous_page": {"default": "mdi:chevron-left"},
      "next_widget": {"default": "mdi:arrow-right-circle"},
      "previous_widget": {"default": "mdi:arrow-left-circle"},
      "dismiss_all_notifications": {"default": "mdi:bell-off"},
      "refresh_dashboard": {"default": "mdi:refresh"}
    },
    "select": {
      "active_page": {"default": "mdi:book-open-page-variant"}
    },
    "sensor": {
      "current_page": {"default": "mdi:book-open-page-variant"},
      "module_count": {"default": "mdi:puzzle"},
      "notification_count": {"default": "mdi:bell-badge"}
    }
  },
  "services": {
    "send_notification": {"service": "mdi:bell-plus"},
    "dismiss_notification": {"service": "mdi:bell-remove"}
  }
}
```

---

## 7. Files Changed

| File | Change |
|---|---|
| `api.py` | Add 11 new methods |
| `coordinator.py` | Extend `_async_update_data` to gather 3 endpoints |
| `__init__.py` | Add `CONFIG_SCHEMA`; add `Platform.BUTTON`, `Platform.SELECT`; add `async_setup` with service registration |
| `sensor.py` | Add `HubbleModuleCountSensor`, `HubbleNotificationCountSensor` |
| `button.py` | New file — 6 button entities |
| `select.py` | New file — `HubblePageSelectEntity` |
| `services.yaml` | New file — service field selectors |
| `strings.json` + `translations/en.json` | Add `"services"` top-level key; add all new entity names |
| `icons.json` | Add service icons |

---

## 8. Error Handling

- All new API methods: `aiohttp.ClientError` → `HubbleConnectionError`; HTTP 401 → `HubbleAuthError`
- HTTP 204 on next/previous widget: API method returns `None` silently (no selectable widgets)
- Button `async_press` and select `async_select_option`: exceptions propagate to HA, which surfaces them in the UI
- Service handlers: `ServiceValidationError` for lookup/state failures; `HomeAssistantError` for API failures
- Coordinator gather: `HubbleAuthError` → `ConfigEntryAuthFailed`; `HubbleConnectionError` → `UpdateFailed`

---

## 9. Testing

| File | Coverage |
|---|---|
| `test_button.py` | One test per button: mock API method, press, assert called + refresh triggered |
| `test_select.py` | Options are slugs; selecting option calls `async_set_active_page` with correct ID; `extra_state_attributes` includes page name |
| `test_sensor.py` | Extend `MOCK_STATE` with `modules` + `notificationCount`; test both new sensors |
| `test_services.py` | `send_notification` returns `notification_id`; `dismiss_notification` calls correct API method; entry-not-found raises `ServiceValidationError`; entry-not-loaded raises `ServiceValidationError` |

All tests use existing `MockConfigEntry` + `AsyncMock` patterns from `conftest.py`.
