# GitHub Copilot & Claude Code Instructions

This repository contains the core of Home Assistant, a Python 3 based home automation application.

## Code Review Guidelines

**Git commit practices during review:**
- **Do NOT amend, squash, or rebase commits after review has started** - Reviewers need to see what changed since their last review

## Development Commands

.vscode/tasks.json contains useful commands used for development.

## Python Syntax Notes

- Python 3.14 explicitly allows `except TypeA, TypeB:` without parentheses.

## Testing

When writing or modifying tests, ensure all test function parameters have type annotations.
Prefer concrete types (for example, `HomeAssistant`, `MockConfigEntry`, etc.) over `Any`.

## Good practices

Integrations with Platinum or Gold level in the Integration Quality Scale reflect a high standard of code quality and maintainability. When looking for examples of something, these are good places to start. The level is indicated in the manifest.json of the integration.

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

### Pre-commit hooks

The pre-commit suite runs ruff, ruff-format, mypy, and pylint on every commit. **Always run lint before committing** to catch issues early:

```bash
ruff check --fix homeassistant/components/hubble/ tests/components/hubble/
ruff format homeassistant/components/hubble/ tests/components/hubble/
```

Common pylint failures to watch for:
- **`hass-argument-type`**: Any helper function in tests that accepts `hass` must type it as `hass: HomeAssistant`, not plain `hass`.
- **Unused imports / unsorted imports**: ruff `--fix` handles these automatically.

`./script/lint_and_test.py` compares against `upstream/dev` which doesn't exist in this devcontainer — it will report no changed files. Run ruff and pytest directly instead.

### Known dev environment issue
The `hassfest` pre-commit hook requires `libturbojpeg` (system library) which is not installed in this devcontainer. Use `--no-verify` when committing changes that trigger hassfest (i.e. changes to `homeassistant/components/hubble/` alongside generated files). The CI pipeline runs hassfest correctly.
