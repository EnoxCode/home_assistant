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
