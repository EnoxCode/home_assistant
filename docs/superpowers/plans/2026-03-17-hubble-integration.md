# Hubble Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a new Home Assistant integration for the Hubble local kitchen dashboard, with a config flow UI, a polling coordinator, and a "current page" sensor.

**Architecture:** A thin `HubbleApiClient` in `api.py` handles all HTTP calls via HA's shared `aiohttp` session. A `HubbleCoordinator` polls `GET /api/dashboard/state` every 30 seconds and stores the full dashboard state. A single sensor reads the active page name from coordinator data. The config flow validates credentials at setup time and supports re-authentication when the API key changes.

**Tech Stack:** Python 3.13, Home Assistant `DataUpdateCoordinator`, `aiohttp` (via `async_get_clientsession`), `pytest` + `pytest-asyncio`, `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-03-17-hubble-integration-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `homeassistant/components/hubble/__init__.py` | Create | Entry setup/unload |
| `homeassistant/components/hubble/manifest.json` | Create | Integration metadata |
| `homeassistant/components/hubble/const.py` | Create | Domain constants |
| `homeassistant/components/hubble/api.py` | Create | HTTP client + custom exceptions |
| `homeassistant/components/hubble/coordinator.py` | Create | DataUpdateCoordinator |
| `homeassistant/components/hubble/config_flow.py` | Create | Config flow + reauth |
| `homeassistant/components/hubble/sensor.py` | Create | Current page sensor |
| `homeassistant/components/hubble/strings.json` | Create | UI strings |
| `homeassistant/components/hubble/icons.json` | Create | Entity icons |
| `tests/components/hubble/__init__.py` | Create | Test package + shared fixtures data |
| `tests/components/hubble/conftest.py` | Create | Shared pytest fixtures |
| `tests/components/hubble/test_config_flow.py` | Create | Config flow tests |
| `tests/components/hubble/test_sensor.py` | Create | Sensor tests |

---

## Task 1: Static files — manifest, const, strings, icons

**Files:**
- Create: `homeassistant/components/hubble/manifest.json`
- Create: `homeassistant/components/hubble/const.py`
- Create: `homeassistant/components/hubble/strings.json`
- Create: `homeassistant/components/hubble/icons.json`

These files have no logic and require no tests. Create them all, then commit.

- [ ] **Step 1: Create `manifest.json`**

```json
{
  "domain": "hubble",
  "name": "Hubble",
  "codeowners": [],
  "config_flow": true,
  "documentation": "https://www.home-assistant.io/integrations/hubble",
  "integration_type": "hub",
  "iot_class": "local_polling",
  "requirements": []
}
```

- [ ] **Step 2: Create `const.py`**

```python
"""Constants for the Hubble integration."""

from datetime import timedelta

DOMAIN = "hubble"
DEFAULT_PORT = 3000
SCAN_INTERVAL = timedelta(seconds=30)
```

- [ ] **Step 3: Create `strings.json`**

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

- [ ] **Step 4: Create `icons.json`**

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

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/
git commit -m "feat(hubble): add static integration files (manifest, const, strings, icons)"
```

---

## Task 2: API client (`api.py`)

**Files:**
- Create: `homeassistant/components/hubble/api.py`

No test file for this task — the client is exercised through coordinator and config flow tests. The exceptions and client structure are verified indirectly.

- [ ] **Step 1: Create `api.py`**

```python
"""Hubble API client."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)


class HubbleError(HomeAssistantError):
    """Base exception for Hubble errors."""


class HubbleAuthError(HubbleError):
    """Raised when the API key is invalid (HTTP 401)."""


class HubbleConnectionError(HubbleError):
    """Raised when the Hubble device cannot be reached."""


class HubbleApiClient:
    """Thin HTTP client for the Hubble REST API."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialise the client."""
        self._base_url = f"http://{host}:{port}"
        self._headers = {"x-api-key": api_key}
        self._session = session

    async def async_get_state(self) -> dict[str, Any]:
        """Return the full dashboard state from GET /api/dashboard/state."""
        url = f"{self._base_url}/api/dashboard/state"
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

- [ ] **Step 2: Commit**

```bash
git add homeassistant/components/hubble/api.py
git commit -m "feat(hubble): add HubbleApiClient with get_state and custom exceptions"
```

---

## Task 3: Coordinator (`coordinator.py`)

**Files:**
- Create: `homeassistant/components/hubble/coordinator.py`

- [ ] **Step 1: Create `coordinator.py`**

```python
"""DataUpdateCoordinator for Hubble."""

from __future__ import annotations

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
        """Fetch latest state from Hubble."""
        try:
            return await self.client.async_get_state()
        except HubbleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except HubbleConnectionError as err:
            raise UpdateFailed(f"Cannot connect to Hubble: {err}") from err
```

- [ ] **Step 2: Commit**

```bash
git add homeassistant/components/hubble/coordinator.py
git commit -m "feat(hubble): add HubbleCoordinator polling dashboard state every 30s"
```

---

## Task 4: Entry setup (`__init__.py`)

**Files:**
- Create: `homeassistant/components/hubble/__init__.py`

- [ ] **Step 1: Create `__init__.py`**

```python
"""The Hubble integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HubbleApiClient
from .coordinator import HubbleConfigEntry, HubbleCoordinator

PLATFORMS = [Platform.SENSOR]


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
    # UpdateFailed is automatically converted to ConfigEntryNotReady here,
    # scheduling a retry — no explicit try/except needed.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Unload a Hubble config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 2: Commit**

```bash
git add homeassistant/components/hubble/__init__.py
git commit -m "feat(hubble): add async_setup_entry and async_unload_entry"
```

---

## Task 5: Config flow (`config_flow.py`) — write tests first

**Files:**
- Create: `tests/components/hubble/__init__.py`
- Create: `tests/components/hubble/conftest.py`
- Create: `tests/components/hubble/test_config_flow.py`
- Create: `homeassistant/components/hubble/config_flow.py`

- [ ] **Step 1: Create test package `__init__.py`**

```python
"""Tests for the Hubble integration."""

MOCK_USER_INPUT = {
    "host": "kitchen-screen",
    "port": 3000,
    "api_key": "test-api-key",
}

MOCK_STATE = {
    "activePage": 1,
    "screenOn": True,
    "pages": [{"id": 1, "slug": "home", "name": "Home"}],
    "widgets": [],
    "templateId": "standard",
    "selectedWidgetId": None,
}
```

- [ ] **Step 2: Create `conftest.py`**

```python
"""Shared fixtures for Hubble tests."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT

from tests.common import MockConfigEntry

from homeassistant.components.hubble.const import DOMAIN

from . import MOCK_STATE, MOCK_USER_INPUT


@pytest.fixture
def mock_hubble_client():
    """Patch HubbleApiClient so no real HTTP calls are made."""
    with patch(
        "homeassistant.components.hubble.config_flow.HubbleApiClient"
    ) as mock_cls:
        client = mock_cls.return_value
        client.async_get_state = AsyncMock(return_value=MOCK_STATE)
        yield client


@pytest.fixture
def mock_config_entry():
    """Return a MockConfigEntry for Hubble."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Hubble (kitchen-screen:3000)",
    )
```

- [ ] **Step 3: Write failing config flow tests**

```python
"""Tests for the Hubble config flow."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from homeassistant.components.hubble.api import HubbleAuthError, HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN

from . import MOCK_STATE, MOCK_USER_INPUT


async def test_user_flow_success(hass: HomeAssistant, mock_hubble_client) -> None:
    """Happy path: valid credentials create a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "homeassistant.components.hubble.HubbleCoordinator"
    ) as mock_coordinator_cls:
        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.data = MOCK_STATE

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hubble (kitchen-screen:3000)"
    assert result["data"] == MOCK_USER_INPUT


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (HubbleAuthError, "invalid_auth"),
        (HubbleConnectionError, "cannot_connect"),
        (Exception, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_hubble_client,
    side_effect,
    expected_error,
) -> None:
    """Errors during validation show correct inline error."""
    mock_hubble_client.async_get_state.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_user_flow_duplicate(
    hass: HomeAssistant, mock_hubble_client, mock_config_entry
) -> None:
    """Duplicate host+port aborts with already_configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_success(
    hass: HomeAssistant, mock_hubble_client, mock_config_entry
) -> None:
    """Re-auth with a new API key updates the entry."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_API_KEY: "new-api-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_API_KEY] == "new-api-key"
```

- [ ] **Step 4: Run tests — expect FAIL (config_flow.py not yet created)**

```bash
pytest tests/components/hubble/test_config_flow.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` for `homeassistant.components.hubble.config_flow`.

- [ ] **Step 5: Create `config_flow.py`**

```python
"""Config flow for the Hubble integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError
from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_API_KEY): str,
    }
)


class HubbleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Hubble config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]}
            )
            try:
                client = HubbleApiClient(
                    host=user_input[CONF_HOST],
                    port=user_input[CONF_PORT],
                    api_key=user_input[CONF_API_KEY],
                    session=async_get_clientsession(self.hass),
                )
                await client.async_get_state()
            except HubbleAuthError:
                errors["base"] = "invalid_auth"
            except HubbleConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error connecting to Hubble")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Hubble ({user_input[CONF_HOST]}:{user_input[CONF_PORT]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Initiate re-auth on API key invalidation."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-auth: accept a new API key."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            new_data = {**reauth_entry.data, **user_input}
            try:
                client = HubbleApiClient(
                    host=reauth_entry.data[CONF_HOST],
                    port=reauth_entry.data[CONF_PORT],
                    api_key=user_input[CONF_API_KEY],
                    session=async_get_clientsession(self.hass),
                )
                await client.async_get_state()
            except HubbleAuthError:
                errors["base"] = "invalid_auth"
            except HubbleConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error re-authenticating with Hubble")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    reauth_entry, data=new_data
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
pytest tests/components/hubble/test_config_flow.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add homeassistant/components/hubble/config_flow.py \
        tests/components/hubble/__init__.py \
        tests/components/hubble/conftest.py \
        tests/components/hubble/test_config_flow.py
git commit -m "feat(hubble): add config flow with user setup and reauth"
```

---

## Task 6: Sensor (`sensor.py`) — write tests first

**Files:**
- Create: `tests/components/hubble/test_sensor.py`
- Create: `homeassistant/components/hubble/sensor.py`

- [ ] **Step 1: Write failing sensor tests**

```python
"""Tests for the Hubble sensor platform."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant

from homeassistant.components.hubble.const import DOMAIN
from tests.common import MockConfigEntry

from . import MOCK_STATE, MOCK_USER_INPUT


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """Set up the Hubble integration with a mocked coordinator."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Hubble (kitchen-screen:3000)",
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.hubble.HubbleApiClient"
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_STATE)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_sensor_state(hass: HomeAssistant, setup_integration) -> None:
    """Sensor state is the name of the active page."""
    state = hass.states.get("sensor.hubble_kitchen_screen_3000_current_page")
    assert state is not None
    assert state.state == "Home"
    assert state.attributes["slug"] == "home"
    assert state.attributes["id"] == 1


async def test_sensor_unavailable_no_data(hass: HomeAssistant) -> None:
    """Sensor is unavailable when coordinator has no data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Hubble (kitchen-screen:3000)",
    )
    entry.add_to_hass(hass)

    with patch(
        "homeassistant.components.hubble.HubbleApiClient"
    ) as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_state = AsyncMock(
            side_effect=Exception("boom")
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.hubble_kitchen_screen_3000_current_page")
    # Entry won't load when first refresh fails — sensor won't exist
    assert state is None


async def test_sensor_unavailable_page_not_found(
    hass: HomeAssistant, setup_integration
) -> None:
    """Sensor is unavailable when activePage id is not in pages list."""
    # Simulate coordinator data where activePage doesn't match any page
    coordinator = hass.data.get(DOMAIN)
    if coordinator is None:
        # coordinator stored in runtime_data
        entry = setup_integration
        coordinator = entry.runtime_data

    bad_state = {**MOCK_STATE, "activePage": 999}
    coordinator.async_set_updated_data(bad_state)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.hubble_kitchen_screen_3000_current_page")
    assert state is not None
    assert state.state == "unavailable"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
pytest tests/components/hubble/test_sensor.py -v
```

Expected: import or setup errors because `sensor.py` doesn't exist yet.

- [ ] **Step 3: Create `sensor.py`**

```python
"""Hubble sensor platform — current page."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
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
    async_add_entities([HubbleCurrentPageSensor(coordinator, entry)])


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Hubble ({entry.data[CONF_HOST]}:{entry.data[CONF_PORT]})",
            manufacturer="Hubble",
        )

    def _current_page(self) -> dict[str, Any] | None:
        """Return the page dict matching activePage, or None."""
        data = self.coordinator.data
        if not data:
            return None
        active_id = data.get("activePage")
        return next(
            (p for p in data.get("pages", []) if p["id"] == active_id), None
        )

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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/components/hubble/test_sensor.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/sensor.py \
        tests/components/hubble/test_sensor.py
git commit -m "feat(hubble): add current page sensor"
```

---

## Task 7: Full test run

- [ ] **Step 1: Run all Hubble tests**

```bash
pytest tests/components/hubble/ -v
```

Expected: all tests PASS, no warnings about missing translation keys.

- [ ] **Step 2: Run linting**

```bash
ruff check homeassistant/components/hubble/ tests/components/hubble/
ruff format --check homeassistant/components/hubble/ tests/components/hubble/
```

Fix any issues, then re-run to confirm clean.

- [ ] **Step 3: Final commit if any lint fixes were made**

```bash
git add -p
git commit -m "chore(hubble): fix lint issues"
```

---

## Done

At this point the integration is complete and tested:

- `Settings → Integrations → Add → Hubble` shows the setup form
- Entering host, port, and API key validates against the live Hubble API
- A `sensor.hubble_<host>_<port>_current_page` entity reports the active page name with `slug` and `id` attributes
- The entity goes unavailable if Hubble is unreachable
- Re-auth flow triggers automatically if the API key is rotated

Future work (separate specs): screen switch, navigation buttons, page select, notifications service.
