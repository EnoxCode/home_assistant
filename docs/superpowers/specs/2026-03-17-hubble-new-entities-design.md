# Hubble Integration: New Entities & Actions

**Date:** 2026-03-17
**Branch:** hubble-integration
**Status:** Approved

---

## Overview

Extend the Hubble Home Assistant integration with navigation buttons, a page selector, additional sensors, and two service actions for notification management. All new entities read from an extended single coordinator. Services are registered in `async_setup`.

---

## 1. Data Layer

### 1.1 Coordinator Extension

`HubbleCoordinator._async_update_data` is extended to call three endpoints in parallel using `asyncio.gather`:

- `GET /api/dashboard/state` (existing)
- `GET /api/dashboard/notify/count`
- `GET /api/modules/`

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

- **Options:** `[page["name"] for page in coordinator.data["pages"]]` — the pages list from `/api/dashboard/state` already excludes hidden pages
- **Current option:** name of the page whose `id` == `coordinator.data["activePage"]`
- **On select:** finds the `page_id` matching the selected name, calls `async_set_active_page(page_id)`, then `coordinator.async_request_refresh()`
- **Unique ID suffix:** `_active_page`

### 2.3 Sensors (`sensor.py`) — 2 new sensors

**`HubbleModuleCountSensor`**
- `native_value`: `len(coordinator.data.get("modules", []))`
- `state_class`: `SensorStateClass.MEASUREMENT`
- `extra_state_attributes`: `{"modules": [m["name"] for m in modules]}`
- Unique ID suffix: `_module_count`

**`HubbleNotificationCountSensor`**
- `native_value`: `coordinator.data.get("notificationCount")`
- `state_class`: `SensorStateClass.MEASUREMENT`
- Unique ID suffix: `_notification_count`

---

## 3. Service Actions

Registered in `async_setup` (not `async_setup_entry`) so they are always available for automation validation even with no loaded config entries.

### 3.1 `hubble.send_notification`

Sends a notification overlay to a Hubble dashboard.

**Target:** `config_entry_id` (ConfigEntrySelector, integration: `hubble`)

**Fields:**

| Field | Required | Type | Notes |
|---|---|---|---|
| `title` | yes | `str` | Short heading |
| `message` | yes | `str` | Body text; supports `**bold**`, `*italic*`, `` `code` `` |
| `level` | no | enum | `info` / `warning` / `error` / `critical` (default: `info`) |
| `permanent` | no | `bool` | Persists until dismissed (mutually exclusive with `timer`) |
| `timer` | no | `int ≥ 1` | Seconds until auto-dismiss (mutually exclusive with `permanent`) |
| `image` | no | `str` | URL or base64 data URI |

**Response:** `{"notification_id": "<uuid>"}` — captured via `response_variable` in automations, used as input to `dismiss_notification`.

Registered with `supports_response=SupportsResponse.OPTIONAL`. Handler checks `call.return_response` before returning data.

### 3.2 `hubble.dismiss_notification`

Dismisses a single active notification by ID.

**Target:** `config_entry_id` (ConfigEntrySelector, integration: `hubble`)

**Fields:**

| Field | Required | Type | Notes |
|---|---|---|---|
| `notification_id` | yes | `str` | UUID returned by `send_notification` |

No response data. Calls `async_dismiss_notification(notification_id)` then triggers a coordinator refresh.

### 3.3 Service Handler Pattern

Both handlers:
1. Look up the config entry: `hass.config_entries.async_get_entry(call.data["config_entry_id"])`
2. Get coordinator: `entry.runtime_data`
3. Call the API method
4. Raise `HomeAssistantError` (not raw exceptions) on failure

---

## 4. Files Changed

| File | Change |
|---|---|
| `api.py` | Add 11 new methods |
| `coordinator.py` | Extend `_async_update_data` to gather 3 endpoints |
| `__init__.py` | Add `Platform.BUTTON`, `Platform.SELECT`; add `async_setup` with service registration |
| `sensor.py` | Add `HubbleModuleCountSensor`, `HubbleNotificationCountSensor` |
| `button.py` | New file — 6 button entities |
| `select.py` | New file — `HubblePageSelectEntity` |
| `services.yaml` | New file — service field descriptions and selectors |
| `strings.json` + `translations/en.json` | Add entity names for all new entities and service translations |
| `icons.json` | Add service icons for `send_notification` and `dismiss_notification` |

---

## 5. Error Handling

- All new API methods: `aiohttp.ClientError` → `HubbleConnectionError`; HTTP 401 → `HubbleAuthError`
- HTTP 204 on next/previous widget: API method returns `None` silently (no error — means no selectable widgets)
- Button `async_press` and select `async_select_option`: exceptions propagate to HA, which surfaces them in the UI
- Service handlers: catch `HubbleError` and re-raise as `HomeAssistantError` so automations receive a meaningful error

---

## 6. Testing

| File | Coverage |
|---|---|
| `test_button.py` | One test per button: mock API method, press, assert called + refresh triggered |
| `test_select.py` | Options match pages list; selecting option calls `async_set_active_page` with correct ID |
| `test_sensor.py` | Extend `MOCK_STATE` with `modules` + `notificationCount`; test both new sensors |
| `test_services.py` | `send_notification` returns `notification_id`; `dismiss_notification` calls correct API method; error cases |

All tests use existing `MockConfigEntry` + `AsyncMock` patterns from `conftest.py`.
