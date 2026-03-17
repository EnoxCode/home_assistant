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
