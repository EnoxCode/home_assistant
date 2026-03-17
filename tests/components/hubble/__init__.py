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

MOCK_NOTIFY_COUNT = 2

# Merged coordinator.data (what _async_update_data returns — no "modules" key)
MOCK_STATE = {
    **MOCK_DASHBOARD_STATE,
    "notificationCount": MOCK_NOTIFY_COUNT,
}

# Discovery payload from GET /api/ws/events
MOCK_DISCOVERY = {
    "core": {
        "events": [
            {"event": "page:changed", "description": "Active page changed.", "payload": {}},
            {"event": "notification", "description": "Notification pushed.", "payload": {}},
            {
                "event": "notification:dismissed",
                "description": "Notification dismissed.",
                "payload": {},
            },
        ]
    },
    "modules": [
        {
            "module": "hubble-clock",
            "version": "0.2.0",
            "description": "Clock widget.",
            "events": [],
            "endpoints": [],
            "instances": [
                {"widgetId": 1, "visualization": "digital", "config": {"slug": "clock-1"}}
            ],
        },
        {
            "module": "hubble-weather",
            "version": "1.0.0",
            "description": "Weather widget.",
            "events": [],
            "endpoints": [],
            "instances": [
                {"widgetId": 2, "visualization": "current", "config": {"slug": "weather-1"}}
            ],
        },
    ],
}

# Temporary alias — test_sensor.py and test_services.py import this;
# proper refactoring happens in Task 3.
MOCK_MODULES = []
