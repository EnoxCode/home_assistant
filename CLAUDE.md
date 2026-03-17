# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup
```bash
./script/setup        # Complete development setup
./script/bootstrap    # Install development dependencies
```

### Testing
```bash
pytest tests/                                              # Full test suite
pytest tests/components/{domain}/                         # Single integration
pytest tests/components/light/test_init.py::test_func -v  # Single test
pytest -x                                                  # Stop on first failure
./script/lint_and_test.py                                 # Lint + test changed files
./script/lint_and_test.py --skiplint                      # Test changed files only
```

### Linting & Formatting
```bash
./script/lint         # Lint changed Python files (Ruff + PyLint)
ruff check --fix .    # Auto-fix Ruff issues
ruff format .         # Format code
pre-commit run --all-files
```

### Type Checking
```bash
mypy homeassistant/
```

## Architecture

### Structure
- `homeassistant/components/` — ~1,348 integrations, each in its own directory
- `homeassistant/helpers/` — Core abstractions (entity, platform, registries, config validation)
- `homeassistant/util/` — Utilities (async, color, datetime, JSON, unit conversion)
- `homeassistant/const.py` — Shared constants; always use these instead of hardcoding
- `homeassistant/core.py` — The `HomeAssistant` class
- `homeassistant/exceptions.py` — Custom exceptions
- `tests/components/{domain}/` — Integration tests mirror the component structure

### Integration Layout
Each integration under `homeassistant/components/{domain}/` follows this pattern:
- `__init__.py` — Setup and config entry management
- `manifest.json` — Metadata and dependencies
- `const.py` — Domain constants
- `config_flow.py` — UI configuration flow
- `coordinator.py` — `DataUpdateCoordinator` for polling
- `models.py` — TypedDicts and data models
- `{platform}.py` — One file per platform (e.g., `sensor.py`, `light.py`)
- `strings.json` + `translations/` — UI strings

### Key Patterns

**Async I/O**: All external I/O must be async. Never block the event loop. Use `asyncio.gather()` instead of awaiting in loops.

**Update Coordinator**: Use `DataUpdateCoordinator` for polling integrations. Minimum poll intervals: 5s for local network, 60s for cloud.

**Error Handling**:
- Temporary setup failures → raise `ConfigEntryNotReady`
- Permanent setup failures → raise `ConfigEntryError`
- Use exceptions from `homeassistant.exceptions`

**Entity Unique IDs**: Must be stable identifiers (serial number, MAC address, `entry_id + suffix`). Never use IP, hostname, URL, email, or username.

**Unknown values**: Use `None`, not the string `"unknown"` or `"unavailable"`. Implement the `available` property.

**Logging**:
```python
_LOGGER = logging.getLogger(__name__)
# Use lazy logging — no f-strings in log calls
_LOGGER.debug("Processing device %s", device_id)
```
No periods at end of log messages. Don't include the integration name (added automatically).

**Python version**: 3.13+ — use pattern matching, type hints, dataclasses, walrus operator, f-strings.

### PRs
Target the `dev` branch (not `master`).

---

## Hubble Integration

Location: `homeassistant/components/hubble/` | Tests: `tests/components/hubble/`

### What it does
Connects to a local [Hubble](https://github.com/EnoxCode/hubble) kitchen dashboard via its REST API. Polls `GET /api/dashboard/state` every 30 seconds and exposes dashboard state as HA entities.

### API
- Base URL: `http://{host}:{port}` (default port `3000`)
- Auth: `x-api-key` header on every request
- OpenAPI spec: `http://{host}:{port}/api/openapi.json`
- Key endpoint: `GET /api/dashboard/state` — returns `activePage`, `screenOn`, `pages`, `widgets`

### File map
| File | Purpose |
|---|---|
| `api.py` | `HubbleApiClient` — thin HTTP wrapper. Add new API methods here. |
| `coordinator.py` | `HubbleCoordinator` — polls `async_get_state()` every 30s. Also defines `HubbleConfigEntry` type alias. |
| `config_flow.py` | Setup form (name, host, port, API key) + re-auth flow. |
| `sensor.py` | `HubbleCurrentPageSensor` — reports active page name with `slug`/`id` attributes. |
| `const.py` | `DOMAIN`, `DEFAULT_PORT`, `SCAN_INTERVAL` |

### Adding new entities
1. Add API method to `api.py` if a new endpoint is needed
2. Add new platform file (e.g., `switch.py`, `button.py`)
3. Add `Platform.SWITCH` to `PLATFORMS` in `__init__.py`
4. Read data from `entry.runtime_data` (the coordinator) — `coordinator.data` holds the full `GET /api/dashboard/state` response
5. All entities share the same `DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, ...)`

### Running locally
```bash
hass --script ensure_config -c config   # first time only
hass -c config                           # starts on port 40000
```

The integration won't appear in the HA UI "Add Integration" search unless `homeassistant/generated/config_flows.py` and `homeassistant/generated/integrations.json` include `"hubble"`. These are already updated on the `hubble-integration` branch. In CI they are regenerated automatically by `hassfest`.

### Known dev environment issue
The `hassfest` pre-commit hook requires `libturbojpeg` (system library) which is not installed in this devcontainer. Use `--no-verify` when committing changes that trigger hassfest (i.e. changes to `homeassistant/components/hubble/` alongside generated files). The CI pipeline runs hassfest correctly.
