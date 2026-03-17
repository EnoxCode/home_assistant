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
