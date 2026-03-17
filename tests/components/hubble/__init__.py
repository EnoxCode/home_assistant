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

# Timer module instances for hubble-timer tests
MOCK_TIMER_INSTANCES = [
    {"widgetId": 10, "visualization": "countdown", "config": {"slug": "timer-1"}},
    {"widgetId": 11, "visualization": "countdown", "config": {"slug": "timer-2"}},
]

# Discovery payload that includes hubble-timer
MOCK_TIMER_DISCOVERY = {
    **MOCK_DISCOVERY,
    "modules": [
        *MOCK_DISCOVERY["modules"],
        {
            "module": "hubble-timer",
            "version": "1.2.3",
            "description": "Cooking timer.",
            "events": [],
            "endpoints": [],
            "instances": MOCK_TIMER_INSTANCES,
        },
    ],
}
