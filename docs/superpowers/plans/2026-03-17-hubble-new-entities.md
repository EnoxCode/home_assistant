# Hubble New Entities & Actions Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Hubble HA integration with 6 buttons, 1 page selector, 2 sensors, and 2 service actions for notification management.

**Architecture:** A single `DataUpdateCoordinator` polls three endpoints in parallel every 30s and merges the results. Buttons, the select entity, and sensors are `CoordinatorEntity` subclasses. Services are registered in `async_setup` using `ConfigEntrySelector` to target a specific Hubble instance.

**Tech Stack:** Home Assistant core, `aiohttp`, `voluptuous`, Python 3.13+

---

## File Map

**Created:**
- `homeassistant/components/hubble/button.py` — 6 button entities (data-driven with `ButtonEntityDescription`)
- `homeassistant/components/hubble/select.py` — page selector entity
- `homeassistant/components/hubble/services.yaml` — service field descriptions and selectors
- `tests/components/hubble/test_button.py`
- `tests/components/hubble/test_select.py`
- `tests/components/hubble/test_services.py`

**Modified:**
- `homeassistant/components/hubble/api.py` — 11 new API methods
- `homeassistant/components/hubble/coordinator.py` — gather 3 endpoints in `_async_update_data`
- `homeassistant/components/hubble/__init__.py` — `CONFIG_SCHEMA`, `Platform.BUTTON`, `Platform.SELECT`, `async_setup` with services
- `homeassistant/components/hubble/sensor.py` — 2 new sensors
- `homeassistant/components/hubble/strings.json` — all new entity/service/exception strings
- `homeassistant/components/hubble/translations/en.json` — mirrors strings.json
- `homeassistant/components/hubble/icons.json` — entity and service icons
- `tests/components/hubble/__init__.py` — update `MOCK_STATE` with new keys + 2 pages
- `tests/components/hubble/conftest.py` — shared `setup_integration` fixture
- `tests/components/hubble/test_sensor.py` — update fixture usage + add 2 new sensor tests

---

## Task 1: Extend coordinator — multi-endpoint polling

**Files:**
- Modify: `homeassistant/components/hubble/api.py`
- Modify: `homeassistant/components/hubble/coordinator.py`
- Modify: `tests/components/hubble/__init__.py`
- Modify: `tests/components/hubble/conftest.py`
- Modify: `tests/components/hubble/test_sensor.py`

- [ ] **Step 1: Update MOCK_STATE to include the two new keys and a second page**

In `tests/components/hubble/__init__.py`, replace the existing content:

```python
"""Tests for the Hubble integration."""

MOCK_USER_INPUT = {
    "name": "Kitchen Screen",
    "host": "kitchen-screen",
    "port": 3000,
    "api_key": "test-api-key",
}

# Raw response from GET /api/dashboard/state (before coordinator merges)
MOCK_DASHBOARD_STATE = {
    "activePage": 1,
    "screenOn": True,
    "pages": [
        {"id": 1, "slug": "home", "name": "Home"},
        {"id": 2, "slug": "media", "name": "Media"},
    ],
    "widgets": [],
    "templateId": "standard",
    "selectedWidgetId": None,
}

MOCK_MODULES = [
    {"id": 1, "name": "hubble-clock", "version": "0.2.0"},
    {"id": 2, "name": "hubble-weather", "version": "1.0.0"},
]

MOCK_NOTIFY_COUNT = 2

# Merged coordinator.data (what _async_update_data returns)
MOCK_STATE = {
    **MOCK_DASHBOARD_STATE,
    "notificationCount": MOCK_NOTIFY_COUNT,
    "modules": MOCK_MODULES,
}
```

- [ ] **Step 2: Update conftest.py with shared setup_integration fixture**

Replace the content of `tests/components/hubble/conftest.py`:

```python
"""Shared fixtures for Hubble tests."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_MODULES, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT

from tests.common import MockConfigEntry


@pytest.fixture
def mock_hubble_client():
    """Patch HubbleApiClient in config_flow so no real HTTP calls are made."""
    with patch(
        "homeassistant.components.hubble.config_flow.HubbleApiClient"
    ) as mock_cls:
        client = mock_cls.return_value
        client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        yield client


@pytest.fixture
def mock_config_entry():
    """Return a MockConfigEntry for Hubble."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """Set up the Hubble integration with a mocked API client.

    Patches the HubbleApiClient used by __init__.py so no real HTTP calls
    are made. Returns the config entry.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_get_modules = AsyncMock(return_value=MOCK_MODULES)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry
```

- [ ] **Step 3: Write failing tests for coordinator multi-endpoint polling**

Add to `tests/components/hubble/test_sensor.py` (replace the existing `setup_integration` fixture with the shared one from conftest, and add new coordinator tests):

```python
"""Tests for the Hubble sensor platform."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_MODULES, MOCK_NOTIFY_COUNT, MOCK_STATE, MOCK_USER_INPUT

from tests.common import MockConfigEntry


async def test_sensor_state(hass: HomeAssistant, setup_integration) -> None:
    """Sensor state is the name of the active page."""
    state = hass.states.get("sensor.kitchen_screen_current_page")
    assert state is not None
    assert state.state == "Home"
    assert state.attributes["slug"] == "home"
    assert state.attributes["id"] == 1


async def test_sensor_unavailable_no_data(hass: HomeAssistant) -> None:
    """Entry fails to load when first refresh raises — sensor entity does not exist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(
            side_effect=HubbleConnectionError("boom")
        )
        mock_client.async_get_notify_count = AsyncMock(return_value=0)
        mock_client.async_get_modules = AsyncMock(return_value=[])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_current_page")
    assert state is None


async def test_sensor_unavailable_page_not_found(
    hass: HomeAssistant, setup_integration
) -> None:
    """Sensor is unavailable when activePage id is not in pages list."""
    entry = setup_integration
    coordinator = entry.runtime_data

    bad_state = {**MOCK_STATE, "activePage": 999}
    coordinator.async_set_updated_data(bad_state)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_current_page")
    assert state is not None
    assert state.state == "unavailable"


async def test_coordinator_fetches_all_endpoints(hass: HomeAssistant) -> None:
    """Coordinator calls all three API methods and merges results."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_get_modules = AsyncMock(return_value=MOCK_MODULES)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_client.async_get_state.assert_called_once()
    mock_client.async_get_notify_count.assert_called_once()
    mock_client.async_get_modules.assert_called_once()

    data = entry.runtime_data.data
    assert data["notificationCount"] == MOCK_NOTIFY_COUNT
    assert data["modules"] == MOCK_MODULES
    assert data["activePage"] == 1
```

- [ ] **Step 4: Run tests — expect failure** (`coordinator` only fetches one endpoint)

```bash
pytest tests/components/hubble/test_sensor.py -v
```

Expected: `test_coordinator_fetches_all_endpoints` FAILS because `coordinator.data` has no `notificationCount` key.

- [ ] **Step 5: Add `async_get_notify_count` and `async_get_modules` to api.py**

Append to the end of `homeassistant/components/hubble/api.py`:

```python
    async def async_get_notify_count(self) -> int:
        """Return the number of currently active notifications."""
        url = f"{self._base_url}/api/dashboard/notify/count"
        try:
            async with self._session.get(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                data = await response.json()
                return data["count"]
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def async_get_modules(self) -> list[dict[str, Any]]:
        """Return the list of installed modules."""
        url = f"{self._base_url}/api/modules/"
        try:
            async with self._session.get(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err
```

- [ ] **Step 6: Extend coordinator to gather three endpoints**

Replace `coordinator.py` content:

```python
"""DataUpdateCoordinator for Hubble."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type HubbleConfigEntry = ConfigEntry[HubbleCoordinator]


class HubbleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Hubble dashboard state."""

    config_entry: HubbleConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HubbleConfigEntry,
        client: HubbleApiClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest state from all Hubble endpoints."""
        try:
            state, notify_count, modules = await asyncio.gather(
                self.client.async_get_state(),
                self.client.async_get_notify_count(),
                self.client.async_get_modules(),
            )
        except HubbleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except HubbleConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return {**state, "notificationCount": notify_count, "modules": modules}
```

- [ ] **Step 7: Run tests — all should pass**

```bash
pytest tests/components/hubble/ -v
```

Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add homeassistant/components/hubble/api.py \
        homeassistant/components/hubble/coordinator.py \
        tests/components/hubble/__init__.py \
        tests/components/hubble/conftest.py \
        tests/components/hubble/test_sensor.py
git commit -m "feat(hubble): extend coordinator to poll notify count and modules"
```

---

## Task 2: New sensors — module count and notification count

**Files:**
- Modify: `homeassistant/components/hubble/sensor.py`
- Modify: `tests/components/hubble/test_sensor.py`

- [ ] **Step 1: Write failing tests for the two new sensors**

Append to `tests/components/hubble/test_sensor.py`:

```python
async def test_module_count_sensor(hass: HomeAssistant, setup_integration) -> None:
    """Module count sensor reports count and module names in attributes."""
    state = hass.states.get("sensor.kitchen_screen_module_count")
    assert state is not None
    assert state.state == "2"
    assert state.attributes["modules"] == ["hubble-clock", "hubble-weather"]


async def test_notification_count_sensor(
    hass: HomeAssistant, setup_integration
) -> None:
    """Notification count sensor reports the active notification count."""
    state = hass.states.get("sensor.kitchen_screen_notification_count")
    assert state is not None
    assert state.state == "2"


async def test_notification_count_updates(
    hass: HomeAssistant, setup_integration
) -> None:
    """Notification count sensor updates when coordinator data changes."""
    coordinator = setup_integration.runtime_data
    coordinator.async_set_updated_data({**MOCK_STATE, "notificationCount": 0})
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_notification_count")
    assert state.state == "0"
```

- [ ] **Step 2: Run tests — expect failure** (entities don't exist yet)

```bash
pytest tests/components/hubble/test_sensor.py::test_module_count_sensor \
       tests/components/hubble/test_sensor.py::test_notification_count_sensor -v
```

Expected: FAIL — entities not found.

- [ ] **Step 3: Add the two new sensors to sensor.py**

Replace `homeassistant/components/hubble/sensor.py`:

```python
"""Hubble sensor platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble sensors from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    async_add_entities([
        HubbleCurrentPageSensor(coordinator, entry),
        HubbleModuleCountSensor(coordinator, entry),
        HubbleNotificationCountSensor(coordinator, entry),
    ])


def _device_info(entry: HubbleConfigEntry) -> DeviceInfo:
    """Return shared DeviceInfo for all Hubble entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, "Hubble"),
        manufacturer="Hubble",
    )


class HubbleCurrentPageSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor reporting the currently active Hubble page."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_page"

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_page"
        self._attr_device_info = _device_info(entry)

    def _current_page(self) -> dict[str, Any] | None:
        """Return the page dict matching activePage, or None."""
        data = self.coordinator.data
        if not data:
            return None
        active_id = data.get("activePage")
        return next((p for p in data.get("pages", []) if p["id"] == active_id), None)

    @property
    def available(self) -> bool:
        """Return False when coordinator data is missing or page not found."""
        return super().available and self._current_page() is not None

    @property
    def native_value(self) -> str | None:
        """Return the name of the currently active page."""
        page = self._current_page()
        return page["name"] if page else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return slug and id of the active page."""
        page = self._current_page()
        if page is None:
            return {}
        return {"slug": page["slug"], "id": page["id"]}


class HubbleModuleCountSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor reporting the number of installed Hubble modules."""

    _attr_has_entity_name = True
    _attr_translation_key = "module_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_module_count"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        """Return the number of installed modules."""
        return len(self.coordinator.data.get("modules", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the names of all installed modules."""
        modules = self.coordinator.data.get("modules", [])
        return {"modules": [m["name"] for m in modules]}


class HubbleNotificationCountSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor reporting the number of active dashboard notifications."""

    _attr_has_entity_name = True
    _attr_translation_key = "notification_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_notification_count"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int | None:
        """Return the number of active notifications."""
        return self.coordinator.data.get("notificationCount")
```

- [ ] **Step 4: Run tests — all should pass**

```bash
pytest tests/components/hubble/test_sensor.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/sensor.py \
        tests/components/hubble/test_sensor.py
git commit -m "feat(hubble): add module count and notification count sensors"
```

---

## Task 3: Navigation API methods + all buttons

**Files:**
- Modify: `homeassistant/components/hubble/api.py`
- Create: `homeassistant/components/hubble/button.py`
- Modify: `homeassistant/components/hubble/__init__.py`
- Create: `tests/components/hubble/test_button.py`

- [ ] **Step 1: Write failing tests for buttons**

Create `tests/components/hubble/test_button.py`:

```python
"""Tests for the Hubble button platform."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_MODULES, MOCK_NOTIFY_COUNT


@pytest.mark.parametrize(
    ("entity_id", "method_name"),
    [
        ("button.kitchen_screen_next_page", "async_next_page"),
        ("button.kitchen_screen_previous_page", "async_previous_page"),
        ("button.kitchen_screen_next_widget", "async_next_widget"),
        ("button.kitchen_screen_previous_widget", "async_previous_widget"),
        ("button.kitchen_screen_dismiss_all_notifications", "async_dismiss_all_notifications"),
        ("button.kitchen_screen_refresh_dashboard", "async_refresh_dashboard"),
    ],
)
async def test_button_press(
    hass: HomeAssistant,
    setup_integration,
    entity_id: str,
    method_name: str,
) -> None:
    """Each button calls the correct API method on press."""
    coordinator = setup_integration.runtime_data

    state = hass.states.get(entity_id)
    assert state is not None

    # Mock the specific API method on the coordinator's client
    mock_method = AsyncMock(return_value={"ok": True})
    setattr(coordinator.client, method_name, mock_method)
    # Patch coordinator refresh to verify it's called after press
    coordinator.async_request_refresh = AsyncMock()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id},
        blocking=True,
    )

    mock_method.assert_called_once()
    coordinator.async_request_refresh.assert_called_once()


async def test_next_widget_204_does_not_raise(
    hass: HomeAssistant, setup_integration
) -> None:
    """Pressing next_widget when no widgets exist (returns None) does not raise."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_next_widget = AsyncMock(return_value=None)

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.kitchen_screen_next_widget"},
        blocking=True,
    )

    coordinator.client.async_next_widget.assert_called_once()
```

- [ ] **Step 2: Run tests — expect failure** (button entities don't exist)

```bash
pytest tests/components/hubble/test_button.py -v
```

Expected: FAIL — entities not found (no button platform).

- [ ] **Step 3: Add navigation and refresh API methods to api.py**

Append to `homeassistant/components/hubble/api.py`:

```python
    async def _async_post(self, path: str, payload: dict | None = None) -> dict[str, Any]:
        """POST to a Hubble endpoint and return the JSON response."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.post(
                url, headers=self._headers, json=payload or {}
            ) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def _async_post_nullable(self, path: str) -> dict[str, Any] | None:
        """POST to an endpoint that may return 204 (no content)."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.post(url, headers=self._headers, json={}) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                if response.status == 204:
                    return None
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def _async_delete(self, path: str) -> dict[str, Any]:
        """DELETE a Hubble endpoint and return the JSON response.

        Note: Hubble DELETE endpoints return HTTP 200 with a JSON body
        (e.g. {"success": true}), not 204. response.json() is safe here.
        """
        url = f"{self._base_url}{path}"
        try:
            async with self._session.delete(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def async_next_page(self) -> dict[str, Any]:
        """Advance to the next visible page."""
        return await self._async_post("/api/dashboard/next-page")

    async def async_previous_page(self) -> dict[str, Any]:
        """Go to the previous visible page."""
        return await self._async_post("/api/dashboard/previous-page")

    async def async_next_widget(self) -> dict[str, Any] | None:
        """Select the next widget. Returns None if no selectable widgets (HTTP 204)."""
        return await self._async_post_nullable("/api/dashboard/widget/next")

    async def async_previous_widget(self) -> dict[str, Any] | None:
        """Select the previous widget. Returns None if no selectable widgets (HTTP 204)."""
        return await self._async_post_nullable("/api/dashboard/widget/previous")

    async def async_set_active_page(self, page_id: int) -> dict[str, Any]:
        """Set the active page by ID."""
        return await self._async_post("/api/dashboard/active-page", {"pageId": page_id})

    async def async_dismiss_all_notifications(self) -> dict[str, Any]:
        """Dismiss all active notifications."""
        return await self._async_delete("/api/dashboard/notify")

    async def async_refresh_dashboard(self) -> dict[str, Any]:
        """Reload the Electron dashboard window."""
        return await self._async_post("/api/dashboard/refresh")

    async def async_send_notification(
        self,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a notification overlay to the dashboard."""
        payload = {"title": title, "message": message, **kwargs}
        return await self._async_post("/api/dashboard/notify", payload)

    async def async_dismiss_notification(self, notification_id: str) -> dict[str, Any]:
        """Dismiss a single notification by UUID."""
        return await self._async_delete(f"/api/dashboard/notify/{notification_id}")
```

- [ ] **Step 4: Create button.py**

Create `homeassistant/components/hubble/button.py`:

```python
"""Hubble button platform."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HubbleApiClient
from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator


@dataclass(frozen=True, kw_only=True)
class HubbleButtonEntityDescription(ButtonEntityDescription):
    """Describes a Hubble button entity."""

    press_fn: Callable[[HubbleApiClient], Coroutine[Any, Any, Any]]


BUTTON_DESCRIPTIONS: tuple[HubbleButtonEntityDescription, ...] = (
    HubbleButtonEntityDescription(
        key="next_page",
        translation_key="next_page",
        press_fn=lambda client: client.async_next_page(),
    ),
    HubbleButtonEntityDescription(
        key="previous_page",
        translation_key="previous_page",
        press_fn=lambda client: client.async_previous_page(),
    ),
    HubbleButtonEntityDescription(
        key="next_widget",
        translation_key="next_widget",
        press_fn=lambda client: client.async_next_widget(),
    ),
    HubbleButtonEntityDescription(
        key="previous_widget",
        translation_key="previous_widget",
        press_fn=lambda client: client.async_previous_widget(),
    ),
    HubbleButtonEntityDescription(
        key="dismiss_all_notifications",
        translation_key="dismiss_all_notifications",
        press_fn=lambda client: client.async_dismiss_all_notifications(),
    ),
    HubbleButtonEntityDescription(
        key="refresh_dashboard",
        translation_key="refresh_dashboard",
        press_fn=lambda client: client.async_refresh_dashboard(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble button entities from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    async_add_entities(
        HubbleButton(coordinator, entry, description)
        for description in BUTTON_DESCRIPTIONS
    )


class HubbleButton(CoordinatorEntity[HubbleCoordinator], ButtonEntity):
    """A Hubble button entity."""

    _attr_has_entity_name = True
    entity_description: HubbleButtonEntityDescription

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
        description: HubbleButtonEntityDescription,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.entity_description.press_fn(self.coordinator.client)
        await self.coordinator.async_request_refresh()
```

- [ ] **Step 5: Add `Platform.BUTTON` to `__init__.py`**

In `homeassistant/components/hubble/__init__.py`, change:

```python
PLATFORMS = [Platform.SENSOR]
```

to:

```python
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
```

- [ ] **Step 6: Run tests — all should pass**

```bash
pytest tests/components/hubble/test_button.py tests/components/hubble/test_sensor.py -v
```

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add homeassistant/components/hubble/api.py \
        homeassistant/components/hubble/button.py \
        homeassistant/components/hubble/__init__.py \
        tests/components/hubble/test_button.py
git commit -m "feat(hubble): add navigation buttons and API methods"
```

---

## Task 4: Page selector entity

**Files:**
- Create: `homeassistant/components/hubble/select.py`
- Modify: `homeassistant/components/hubble/__init__.py`
- Create: `tests/components/hubble/test_select.py`

- [ ] **Step 1: Write failing tests for the page selector**

Create `tests/components/hubble/test_select.py`:

```python
"""Tests for the Hubble select platform."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant

from . import MOCK_STATE


async def test_select_options_are_page_slugs(
    hass: HomeAssistant, setup_integration
) -> None:
    """Select options are page slugs from coordinator data."""
    state = hass.states.get("select.kitchen_screen_active_page")
    assert state is not None
    assert state.state == "home"
    assert state.attributes["options"] == ["home", "media"]
    assert state.attributes["page_name"] == "Home"


async def test_select_current_option_tracks_active_page(
    hass: HomeAssistant, setup_integration
) -> None:
    """Current option updates when coordinator pushes new activePage."""
    coordinator = setup_integration.runtime_data
    coordinator.async_set_updated_data({**MOCK_STATE, "activePage": 2})
    await hass.async_block_till_done()

    state = hass.states.get("select.kitchen_screen_active_page")
    assert state.state == "media"
    assert state.attributes["page_name"] == "Media"


async def test_select_option_calls_set_active_page(
    hass: HomeAssistant, setup_integration
) -> None:
    """Selecting an option calls async_set_active_page with correct page ID."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_set_active_page = AsyncMock(
        return_value={"success": True, "activePage": 2}
    )

    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.kitchen_screen_active_page",
            "option": "media",
        },
        blocking=True,
    )

    coordinator.client.async_set_active_page.assert_called_once_with(2)


async def test_select_unknown_option_does_not_call_api(
    hass: HomeAssistant, setup_integration
) -> None:
    """Selecting an unknown slug silently does nothing."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_set_active_page = AsyncMock()

    # HA's select platform validates options before calling async_select_option,
    # so we test by directly calling the entity method
    entity = next(
        e
        for e in hass.data["entity_components"]["select"].entities
        if e.unique_id and "active_page" in e.unique_id
    )
    await entity.async_select_option("nonexistent-slug")
    coordinator.client.async_set_active_page.assert_not_called()
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/components/hubble/test_select.py -v
```

Expected: FAIL — select entity doesn't exist.

- [ ] **Step 3: Create select.py**

Create `homeassistant/components/hubble/select.py`:

```python
"""Hubble select platform — active page selector."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble select entities from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    async_add_entities([HubblePageSelectEntity(coordinator, entry)])


class HubblePageSelectEntity(CoordinatorEntity[HubbleCoordinator], SelectEntity):
    """Select entity for the active Hubble page (options are page slugs)."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_page"

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active_page"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )

    @property
    def options(self) -> list[str]:
        """Return all page slugs (guaranteed unique by Hubble API)."""
        return [p["slug"] for p in self.coordinator.data.get("pages", [])]

    @property
    def current_option(self) -> str | None:
        """Return the slug of the currently active page."""
        data = self.coordinator.data
        if not data:
            return None
        active_id = data.get("activePage")
        page = next(
            (p for p in data.get("pages", []) if p["id"] == active_id), None
        )
        return page["slug"] if page else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the human-readable name of the active page."""
        data = self.coordinator.data
        if not data:
            return {}
        active_id = data.get("activePage")
        page = next(
            (p for p in data.get("pages", []) if p["id"] == active_id), None
        )
        return {"page_name": page["name"]} if page else {}

    async def async_select_option(self, option: str) -> None:
        """Change the active page by slug."""
        pages = self.coordinator.data.get("pages", [])
        page = next((p for p in pages if p["slug"] == option), None)
        if page is None:
            return
        await self.coordinator.client.async_set_active_page(page["id"])
        await self.coordinator.async_request_refresh()
```

- [ ] **Step 4: Add `Platform.SELECT` to `__init__.py`**

Change:

```python
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]
```

to:

```python
PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR]
```

- [ ] **Step 5: Run tests — all should pass**

```bash
pytest tests/components/hubble/test_select.py tests/components/hubble/test_sensor.py tests/components/hubble/test_button.py -v
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add homeassistant/components/hubble/select.py \
        homeassistant/components/hubble/__init__.py \
        tests/components/hubble/test_select.py
git commit -m "feat(hubble): add active page selector entity"
```

---

## Task 5: Service actions — send and dismiss notification

**Files:**
- Modify: `homeassistant/components/hubble/__init__.py`
- Create: `tests/components/hubble/test_services.py`

- [ ] **Step 1: Write failing tests for the services**

Create `tests/components/hubble/test_services.py`:

```python
"""Tests for Hubble service actions."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.core import HomeAssistant

from homeassistant.components.hubble.const import DOMAIN

from . import MOCK_DASHBOARD_STATE, MOCK_MODULES, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT
from tests.common import MockConfigEntry


async def test_send_notification_returns_id(
    hass: HomeAssistant, setup_integration
) -> None:
    """send_notification returns the notification UUID."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_send_notification = AsyncMock(
        return_value={"id": "abc-123", "success": True}
    )

    result = await hass.services.async_call(
        DOMAIN,
        "send_notification",
        {
            "config_entry_id": setup_integration.entry_id,
            "title": "Motion Detected",
            "message": "Camera triggered",
        },
        return_response=True,
        blocking=True,
    )

    assert result == {"notification_id": "abc-123"}
    coordinator.client.async_send_notification.assert_called_once_with(
        title="Motion Detected",
        message="Camera triggered",
    )


async def test_send_notification_with_optional_fields(
    hass: HomeAssistant, setup_integration
) -> None:
    """send_notification passes optional fields to the API."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_send_notification = AsyncMock(
        return_value={"id": "def-456", "success": True}
    )

    await hass.services.async_call(
        DOMAIN,
        "send_notification",
        {
            "config_entry_id": setup_integration.entry_id,
            "title": "Alert",
            "message": "Something happened",
            "level": "warning",
            "permanent": True,
        },
        blocking=True,
    )

    coordinator.client.async_send_notification.assert_called_once_with(
        title="Alert",
        message="Something happened",
        level="warning",
        permanent=True,
    )


async def test_dismiss_notification_calls_api(
    hass: HomeAssistant, setup_integration
) -> None:
    """dismiss_notification calls async_dismiss_notification with the UUID."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_dismiss_notification = AsyncMock(
        return_value={"success": True}
    )

    await hass.services.async_call(
        DOMAIN,
        "dismiss_notification",
        {
            "config_entry_id": setup_integration.entry_id,
            "notification_id": "abc-123",
        },
        blocking=True,
    )

    coordinator.client.async_dismiss_notification.assert_called_once_with("abc-123")


async def test_send_notification_entry_not_found(hass: HomeAssistant) -> None:
    """send_notification raises ServiceValidationError for unknown entry_id."""
    # Register domain by setting up any entry, then use a fake entry_id
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_get_modules = AsyncMock(return_value=MOCK_MODULES)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "send_notification",
            {
                "config_entry_id": "nonexistent-entry-id",
                "title": "Test",
                "message": "Test",
            },
            blocking=True,
        )


async def test_send_notification_entry_not_loaded(hass: HomeAssistant) -> None:
    """send_notification raises ServiceValidationError when entry exists but is not loaded."""
    # Create an entry but do not set it up (remains in NOT_LOADED state)
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    # Load domain (so async_setup runs and services are registered) via a second entry
    other_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_USER_INPUT, title="Other Screen"
    )
    other_entry.add_to_hass(hass)
    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_get_modules = AsyncMock(return_value=MOCK_MODULES)
        await hass.config_entries.async_setup(other_entry.entry_id)
        await hass.async_block_till_done()

    # entry is added but never set up — state is NOT_LOADED
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "send_notification",
            {
                "config_entry_id": entry.entry_id,
                "title": "Test",
                "message": "Test",
            },
            blocking=True,
        )
```

- [ ] **Step 2: Run tests — expect failure** (services not registered)

```bash
pytest tests/components/hubble/test_services.py -v
```

Expected: FAIL — service `hubble.send_notification` does not exist.

- [ ] **Step 3: Update `__init__.py` with `CONFIG_SCHEMA`, `async_setup`, and services**

Replace `homeassistant/components/hubble/__init__.py`:

```python
"""The Hubble integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HubbleApiClient, HubbleError
from .coordinator import HubbleConfigEntry, HubbleCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema("hubble")

_SEND_NOTIFICATION_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): selector.ConfigEntrySelector(
        {"integration": "hubble"}
    ),
    vol.Required("title"): cv.string,
    vol.Required("message"): cv.string,
    vol.Optional("level", default="info"): vol.In(
        ["info", "warning", "error", "critical"]
    ),
    vol.Exclusive("permanent", "persistence_mode"): cv.boolean,
    vol.Exclusive("timer", "persistence_mode"): vol.All(
        vol.Coerce(int), vol.Range(min=1)
    ),
    vol.Optional("image"): cv.string,
})

_DISMISS_NOTIFICATION_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): selector.ConfigEntrySelector(
        {"integration": "hubble"}
    ),
    vol.Required("notification_id"): cv.string,
})

_OPTIONAL_FIELDS = frozenset({"level", "permanent", "timer", "image"})


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> HubbleCoordinator:
    """Look up the coordinator for a config entry, raising ServiceValidationError on failure."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise ServiceValidationError(
            translation_domain="hubble",
            translation_key="config_entry_not_found",
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain="hubble",
            translation_key="config_entry_not_loaded",
        )
    return entry.runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register Hubble service actions."""

    async def handle_send_notification(call: ServiceCall) -> ServiceResponse | None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        optional = {k: v for k, v in call.data.items() if k in _OPTIONAL_FIELDS}
        try:
            result = await coordinator.client.async_send_notification(
                title=call.data["title"],
                message=call.data["message"],
                **optional,
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()
        if call.return_response:
            return {"notification_id": result["id"]}
        return None

    async def handle_dismiss_notification(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            await coordinator.client.async_dismiss_notification(
                call.data["notification_id"]
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()

    hass.services.async_register(
        "hubble",
        "send_notification",
        handle_send_notification,
        schema=_SEND_NOTIFICATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        "hubble",
        "dismiss_notification",
        handle_dismiss_notification,
        schema=_DISMISS_NOTIFICATION_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Set up Hubble from a config entry."""
    session = async_get_clientsession(hass)
    client = HubbleApiClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        api_key=entry.data[CONF_API_KEY],
        session=session,
    )
    coordinator = HubbleCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Unload a Hubble config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 4: Run tests — all should pass**

```bash
pytest tests/components/hubble/ -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/__init__.py \
        tests/components/hubble/test_services.py
git commit -m "feat(hubble): add send_notification and dismiss_notification service actions"
```

---

## Task 6: Strings, translations, services.yaml, and icons

**Files:**
- Modify: `homeassistant/components/hubble/strings.json`
- Modify: `homeassistant/components/hubble/translations/en.json`
- Create: `homeassistant/components/hubble/services.yaml`
- Modify: `homeassistant/components/hubble/icons.json`

No TDD loop here — these are data files with no logic. Run the full test suite after to confirm nothing breaks.

- [ ] **Step 1: Replace strings.json**

```json
{
  "config": {
    "step": {
      "user": {
        "data": {
          "name": "Name",
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
  },
  "services": {
    "send_notification": {
      "name": "Send notification",
      "description": "Sends a notification overlay to the Hubble dashboard.",
      "fields": {
        "config_entry_id": {
          "name": "Hubble instance",
          "description": "The Hubble dashboard to send the notification to."
        },
        "title": {
          "name": "Title",
          "description": "Short heading displayed at the top of the notification."
        },
        "message": {
          "name": "Message",
          "description": "Body text. Supports **bold**, *italic*, and `code` markdown."
        },
        "level": {
          "name": "Level",
          "description": "Severity level. Determines card colour and icon."
        },
        "permanent": {
          "name": "Permanent",
          "description": "If true, notification stays until dismissed. Mutually exclusive with timer."
        },
        "timer": {
          "name": "Timer",
          "description": "Seconds until auto-dismiss. Mutually exclusive with permanent."
        },
        "image": {
          "name": "Image",
          "description": "Optional image URL or base64 data URI."
        }
      }
    },
    "dismiss_notification": {
      "name": "Dismiss notification",
      "description": "Dismisses a single active notification by its ID.",
      "fields": {
        "config_entry_id": {
          "name": "Hubble instance",
          "description": "The Hubble dashboard to dismiss the notification on."
        },
        "notification_id": {
          "name": "Notification ID",
          "description": "UUID returned by the send_notification action."
        }
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

- [ ] **Step 2: Replace translations/en.json** (exact copy of strings.json — same content)

Copy the same JSON written in Step 1 to `homeassistant/components/hubble/translations/en.json`.

- [ ] **Step 3: Create services.yaml**

Create `homeassistant/components/hubble/services.yaml`:

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

- [ ] **Step 4: Replace icons.json**

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

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/components/hubble/ -v
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add homeassistant/components/hubble/strings.json \
        homeassistant/components/hubble/translations/en.json \
        homeassistant/components/hubble/services.yaml \
        homeassistant/components/hubble/icons.json
git commit -m "feat(hubble): add strings, translations, services.yaml, and icons"
```

---

## Final check

- [ ] **Run the full integration test suite**

```bash
pytest tests/components/hubble/ -v
```

Expected: All pass with no warnings.

- [ ] **Run linting on changed files**

```bash
./script/lint
```

Expected: No errors. If ruff reports issues, run `ruff check --fix homeassistant/components/hubble/` and re-commit.
