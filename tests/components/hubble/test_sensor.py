"""Tests for the Hubble sensor platform."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_NOTIFY_COUNT, MOCK_STATE, MOCK_TIMER_DISCOVERY, MOCK_USER_INPUT

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

    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(
            side_effect=HubbleConnectionError("boom")
        )
        mock_client.async_get_notify_count = AsyncMock(return_value=0)
        mock_client.async_discover = AsyncMock(return_value={"core": {"events": []}, "modules": []})
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
    """Coordinator calls state and notify_count endpoints and merges results."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_discover = AsyncMock(return_value={"core": {"events": []}, "modules": []})
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_client.async_get_state.assert_called_once()
    mock_client.async_get_notify_count.assert_called_once()

    data = entry.runtime_data.data
    assert data["notificationCount"] == MOCK_NOTIFY_COUNT
    assert data["activePage"] == 1
    # "modules" key is no longer in coordinator.data — it lives in coordinator.discovery
    assert "modules" not in data


async def test_module_count_sensor(hass: HomeAssistant, setup_integration) -> None:
    """Module count sensor reports count and module names from discovery data."""
    state = hass.states.get("sensor.kitchen_screen_module_count")
    assert state is not None
    assert state.state == "2"
    # Names come from m["module"] in discovery data, not m["name"]
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


# ── Timer sensor helpers ───────────────────────────────────────────────────────

@asynccontextmanager
async def _setup_with_timer(hass, connector_state=None):
    """Set up the integration with hubble-timer in discovery."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)
    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_discover = AsyncMock(return_value=MOCK_TIMER_DISCOVERY)
        mock_client.async_get_connector_state = AsyncMock(
            return_value=connector_state or {}
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, mock_client


# ── Timer sensor: creation ─────────────────────────────────────────────────────

async def test_timer_sensors_created_for_each_instance(hass: HomeAssistant) -> None:
    """One timer sensor is created per discovered timer instance."""
    async with _setup_with_timer(hass):
        assert hass.states.get("sensor.kitchen_screen_timer_1") is not None
        assert hass.states.get("sensor.kitchen_screen_timer_2") is not None


async def test_timer_sensors_not_created_when_module_absent(
    hass: HomeAssistant, setup_integration
) -> None:
    """No timer sensors when hubble-timer is not in discovery (standard MOCK_DISCOVERY)."""
    assert hass.states.get("sensor.kitchen_screen_timer_1") is None


async def test_timer_sensor_default_state_is_idle(hass: HomeAssistant) -> None:
    """Timer sensor defaults to 'idle' when no connector-state data exists."""
    async with _setup_with_timer(hass):
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "idle"
        assert state.attributes["slug"] == "timer-1"


# ── Timer sensor: initial state from connector-state ──────────────────────────

async def test_timer_sensor_initial_state_paused_from_connector_state(
    hass: HomeAssistant,
) -> None:
    """Timer sensor initialises to paused when connector state has timer:paused."""
    connector_state = {
        "timer:started": {"slug": "timer-1", "mode": "countdown", "duration": 300},
        "timer:paused": {"slug": "timer-1", "elapsed": 120.0},
    }
    async with _setup_with_timer(hass, connector_state=connector_state):
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "paused"
        assert state.attributes["elapsed_seconds"] == 120.0


async def test_timer_sensor_initial_state_active_from_connector_state(
    hass: HomeAssistant,
) -> None:
    """Timer sensor initialises to active when only timer:started is present."""
    connector_state = {
        "timer:started": {
            "slug": "timer-1",
            "mode": "countdown",
            "duration": 300,
            "label": "Pasta",
        },
    }
    async with _setup_with_timer(hass, connector_state=connector_state):
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "active"
        assert state.attributes["mode"] == "countdown"
        assert state.attributes["label"] == "Pasta"


async def test_timer_sensor_initial_state_slug_mismatch_defaults_idle(
    hass: HomeAssistant,
) -> None:
    """Connector-state payload for a different slug does not initialise this sensor."""
    connector_state = {
        "timer:paused": {"slug": "timer-2", "elapsed": 60.0},
    }
    async with _setup_with_timer(hass, connector_state=connector_state):
        # timer-1 has no matching connector-state → stays idle
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "idle"


# ── Timer sensor: WS event state transitions ──────────────────────────────────

async def test_timer_started_event_sets_active_state(hass: HomeAssistant) -> None:
    """timer:started WS event sets state to active with finishes_at."""
    fake_now = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)

    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        with patch(
            "homeassistant.components.hubble.sensor.dt_util.utcnow",
            return_value=fake_now,
        ):
            coordinator._handle_ws_event(
                "module:data",
                {
                    "module": "hubble-timer",
                    "topic": "timer:started",
                    "data": {
                        "slug": "timer-1",
                        "mode": "countdown",
                        "duration": 300,
                        "label": "Pasta",
                    },
                },
            )
            await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "active"
    assert state.attributes["mode"] == "countdown"
    assert state.attributes["label"] == "Pasta"
    assert state.attributes["duration"] == 300
    expected = (fake_now + timedelta(seconds=300)).isoformat()
    assert state.attributes["finishes_at"] == expected


async def test_timer_paused_event_sets_paused_state(hass: HomeAssistant) -> None:
    """timer:paused WS event sets state to paused, stores elapsed, clears finishes_at."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:paused",
                "data": {"slug": "timer-1", "elapsed": 42.0},
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "paused"
    assert state.attributes["elapsed_seconds"] == 42.0
    assert "finishes_at" not in state.attributes


async def test_timer_resumed_recomputes_finishes_at(hass: HomeAssistant) -> None:
    """timer:resumed recomputes finishes_at from remaining = duration - elapsed.

    Drive to paused state via WS events (not connector-state) so that _duration
    is set from timer:started before timer:paused clears finishes_at.
    """
    fake_now = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)

    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        with patch(
            "homeassistant.components.hubble.sensor.dt_util.utcnow",
            return_value=fake_now,
        ):
            # Start timer so _duration = 300 is stored on the sensor
            coordinator._handle_ws_event(
                "module:data",
                {
                    "module": "hubble-timer",
                    "topic": "timer:started",
                    "data": {"slug": "timer-1", "mode": "countdown", "duration": 300},
                },
            )
            # Pause it — _duration stays set, _finishes_at cleared
            coordinator._handle_ws_event(
                "module:data",
                {
                    "module": "hubble-timer",
                    "topic": "timer:paused",
                    "data": {"slug": "timer-1", "elapsed": 60.0},
                },
            )
            # Resume — should recompute finishes_at = now + (300 - 60)
            coordinator._handle_ws_event(
                "module:data",
                {
                    "module": "hubble-timer",
                    "topic": "timer:resumed",
                    "data": {"slug": "timer-1", "elapsed": 60.0},
                },
            )
            await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "active"
    # remaining = 300 - 60 = 240
    expected = (fake_now + timedelta(seconds=240)).isoformat()
    assert state.attributes["finishes_at"] == expected


async def test_timer_finished_event(hass: HomeAssistant) -> None:
    """timer:finished WS event sets state to finished, clears finishes_at."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:finished",
                "data": {"slug": "timer-1", "label": "Done", "duration": 300},
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "finished"
    assert "finishes_at" not in state.attributes


async def test_timer_reset_event_clears_state(hass: HomeAssistant) -> None:
    """timer:reset WS event returns sensor to idle, clears all attributes."""
    connector_state = {
        "timer:started": {"slug": "timer-1", "mode": "countdown", "duration": 300, "label": "Test"},
    }
    async with _setup_with_timer(hass, connector_state=connector_state) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:reset",
                "data": {"slug": "timer-1"},
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "idle"
    assert "label" not in state.attributes
    assert "mode" not in state.attributes
    assert "duration" not in state.attributes
    assert "finishes_at" not in state.attributes
    assert "elapsed_seconds" not in state.attributes


# ── Timer sensor: slug dispatch ────────────────────────────────────────────────

async def test_ws_event_for_one_slug_does_not_affect_other(
    hass: HomeAssistant,
) -> None:
    """WS event for timer-1 slug does not change timer-2 sensor state."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:paused",
                "data": {"slug": "timer-1", "elapsed": 10.0},
            },
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.kitchen_screen_timer_1").state == "paused"
    assert hass.states.get("sensor.kitchen_screen_timer_2").state == "idle"


async def test_pending_module_sub_registered_when_timer_discovered(
    hass: HomeAssistant,
) -> None:
    """add_pending_module_subscription is called for hubble-timer when discovered."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        assert "hubble-timer" in coordinator._pending_module_subs
