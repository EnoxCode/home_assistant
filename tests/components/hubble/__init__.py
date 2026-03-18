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

# Mock response from GET /api/commands/{slug}/execute
MOCK_COMMAND_EXECUTE_RESULT = {
    "ok": True,
    "stdout": "true",
    "stderr": "",
    "exitCode": 0,
}

# Discovery payload from GET /api/ws/events
MOCK_DISCOVERY = {
    "core": {
        "events": [
            {
                "event": "page:changed",
                "description": "Active page changed.",
                "payload": {},
            },
            {
                "event": "notification",
                "description": "Notification pushed.",
                "payload": {},
            },
            {
                "event": "notification:dismissed",
                "description": "Notification dismissed.",
                "payload": {},
            },
        ]
    },
    "commands": [
        {
            "slug": "screen-off",
            "label": "Screen Off",
            "description": "Turns off the display.",
            "builtin": True,
            "executeUrl": "/api/commands/screen-off/execute",
        },
        {
            "slug": "screen-on",
            "label": "Screen On",
            "description": "Turns on the display.",
            "builtin": True,
            "executeUrl": "/api/commands/screen-on/execute",
        },
        {
            "slug": "screen-status",
            "label": "Screen Status",
            "description": "Prints true/false to stdout.",
            "builtin": True,
            "executeUrl": "/api/commands/screen-status/execute",
        },
        {
            "slug": "test-command",
            "label": "Test Command",
            "description": "A user-defined test command.",
            "builtin": False,
            "executeUrl": "/api/commands/test-command/execute",
        },
    ],
    "modules": [
        {
            "module": "hubble-clock",
            "version": "0.2.0",
            "description": "Clock widget.",
            "events": [],
            "endpoints": [],
            "instances": [
                {
                    "widgetId": 1,
                    "visualization": "digital",
                    "config": {"slug": "clock-1"},
                }
            ],
        },
        {
            "module": "hubble-weather",
            "version": "1.0.0",
            "description": "Weather widget.",
            "events": [],
            "endpoints": [],
            "instances": [
                {
                    "widgetId": 2,
                    "visualization": "current",
                    "config": {"slug": "weather-1"},
                }
            ],
        },
    ],
}

MOCK_MEDIA_STATE = {
    "state": "playing",
    "mediaContentId": "http://nas.local/track.mp3",
    "mediaContentType": "audio",
    "mediaTitle": "Bohemian Rhapsody",
    "mediaArtist": "Queen",
    "mediaImageUrl": "http://nas.local/covers/queen.jpg",
    "mediaDuration": 354.0,
    "mediaPosition": 42.0,
    "mediaPositionUpdatedAt": "2026-03-17T10:23:45.123+00:00",
    "volumeLevel": 0.7,
    "isVolumeMuted": False,
    "displayMode": "none",
    "source": "default",
    "sourceList": [
        {"id": "default", "label": "Default"},
        {"id": "hdmi", "label": "HDMI Output"},
    ],
    "announcing": False,
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
