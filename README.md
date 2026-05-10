# moixa-py

Unofficial Python client for the Moixa GridShare API, reverse-engineered from the Android app and live browser traffic. Authenticates using Cognito User Pool SRP, exchanges tokens for temporary AWS credentials via the Cognito Identity Pool, and signs API requests with SigV4, matching the mobile app's auth flow exactly.

## Install

```bash
pip install .
# or with dev dependencies (includes pytest)
pip install ".[dev]"
```

Runtime dependencies: `pycognito`, `aws-requests-auth`, `boto3`, `requests`.

## Quick start

```python
from moixa_py import MoixaCognitoAuth, MoixaClient, TokenStore

auth = MoixaCognitoAuth('you@example.com', 'yourpassword')
tokens = auth.login()
TokenStore().save(tokens)  # saves to ~/.moixa_tokens.json

client = MoixaClient(tokens)

site_users = client.get_site_users()
site_id = site_users[0]['siteId']
battery_id = next(
    d['id'] for d in site_users[0]['devices']
    if d['deviceType'] == 'VirtualMoixaVictronSmartBattery'
)

print(client.get_current_battery_level())        # e.g. 0.73
print(client.get_device_current_operation_mode(battery_id)['mode'])  # 'smart'
```

Subsequent runs can skip re-authenticating:

```python
tokens = TokenStore().load()
client = MoixaClient(tokens)
```

## API reference

### Auth

| Class / function | Description |
|---|---|
| `MoixaCognitoAuth(username, password)` | Authenticates via Cognito SRP |
| `.login()` | Returns a `CognitoTokens` object |
| `refresh_tokens(tokens)` | Refreshes access+id tokens using a saved refresh token |
| `TokenStore(path=None)` | Save/load tokens to `~/.moixa_tokens.json` by default |
| `.save(tokens)` | Write tokens to disk |
| `.load()` | Read tokens from disk; raises `MoixaAuthError` if missing |

### Account

| Method | Returns |
|---|---|
| `get_site_users()` | List of sites with device IDs and types |
| `get_user_metadata()` | Account info: email, vendor, status, created date |

### Readings

| Method | Returns |
|---|---|
| `get_current_battery_level()` | SOC as a float, 0.0-1.0 |
| `get_core_readings(site_id, time_range='latest')` | Power flows: consumption, grid in/out, solar, storage in/out |
| `get_device_status(device_id, time_range='latest')` | Per-device readings: consumption, grid, production, storage W, SOC |
| `get_device(device_id)` | Full device info including attributes (capacity, hub, min SOC settings) |

`time_range` accepts `'latest'` or an ISO 8601 interval: `'2026-05-09T23:00:00.000Z,2026-05-10T23:00:00.000Z'`.

### Battery control

| Method | Description |
|---|---|
| `get_device_current_operation_mode(device_id)` | Returns current mode and active plan |
| `set_device_operation_mode(device_id, mode)` | Switch mode: `'smart'`, `'schedule'`, or `'simple'` |
| `get_device_operation_schedule(device_id)` | Returns the full weekly 7-day schedule plan |
| `set_device_operation_schedule(device_id, plan)` | Replace the entire schedule plan |

### Schedule slot helpers

All three helpers are read-modify-write wrappers: they fetch the current schedule, modify the `intents` list, and PUT the result back.

| Method | Description |
|---|---|
| `add_schedule_intent(device_id, kind, duration_minutes, position=-1, ...)` | Insert a new slot; time is taken from the neighbouring slot |
| `edit_schedule_intent(device_id, index, ...)` | Update fields on an existing slot; duration changes are absorbed by the neighbour |
| `delete_schedule_intent(device_id, index)` | Remove a slot; its duration is returned to the neighbouring slot |

**Intent kinds:**

| kind | Required fields | Optional fields |
|---|---|---|
| `'balance'` | - | `soc_min`, `soc_max`, `power_watts_min` (default -20), `power_watts_max` (default 20) |
| `'charge/discharge'` | `power_watts` | `soc_min`, `soc_max` |
| `'idle'` | - | `soc_min`, `soc_max` |

```python
# Add a 1-hour idle slot at position 2
client.add_schedule_intent(battery_id, kind='idle', duration_minutes=60, position=2)

# Edit slot 0: raise minimum SOC to 20%
client.edit_schedule_intent(battery_id, index=0, soc_min=0.2)

# Delete slot 2 (time is returned to slot 1)
client.delete_schedule_intent(battery_id, index=2)

# Switch to schedule mode
client.set_device_operation_mode(battery_id, 'schedule')
```

### History

| Method | Returns |
|---|---|
| `get_device_intent_time_series(device_id, start, end)` | Planned charge/discharge intents over a date range |
| `get_device_tariff_time_series(device_id, start, end)` | Tariff prices over a date range (e.g. Octopus Agile) |

`start` and `end` are ISO 8601 strings, e.g. `'2026-05-10T00:00:00.000+01:00'`.

## CLI

Requires tokens saved by `TokenStore` (default path: `~/.moixa_tokens.json`).

```bash
moixa load                      # print saved token info
moixa sites                     # list site users and devices
moixa battery                   # show current battery level
moixa device <device_id>        # get device status
```

All commands accept `--token-file <path>` to use a non-default token file.

## Tests

```bash
pip install ".[dev]"
pytest
```

Tests cover `CognitoTokens`, `TokenStore`, `_build_intent`, and all three schedule slot helpers. No network calls are made.

## Caveat

This is unofficial, based on static analysis of the Moixa Android app and captured browser traffic. The API may change without notice.
