"""Constants for the Hubble integration."""

from datetime import timedelta

DOMAIN = "hubble"
DEFAULT_PORT = 3000
SCAN_INTERVAL = timedelta(minutes=5)

# Screen command config keys and defaults.
CONF_SCREEN_ON_COMMAND = "screen_on_command"
CONF_SCREEN_OFF_COMMAND = "screen_off_command"
CONF_SCREEN_STATUS_COMMAND = "screen_status_command"
CONF_SCREEN_POLL_INTERVAL = "screen_poll_interval"

DEFAULT_SCREEN_ON_COMMAND = "screen-on"
DEFAULT_SCREEN_OFF_COMMAND = "screen-off"
DEFAULT_SCREEN_STATUS_COMMAND = "screen-status"
DEFAULT_SCREEN_POLL_INTERVAL = 30  # seconds
