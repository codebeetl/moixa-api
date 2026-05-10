# moixa-py

Unofficial Python client for the Moixa GridShare API, reverse-engineered from the Android app and live browser traffic. Authenticates using Cognito User Pool SRP, exchanges tokens for temporary AWS credentials via the Cognito Identity Pool, and signs API requests with SigV4, matching the mobile app's auth flow exactly.

## Install

```bash
pip install .
```

Dependencies: `pycognito`, `aws-requests-auth`, `boto3`, `requests`.

## Usage

```python
from moixa_py import MoixaCognitoAuth, MoixaClient, TokenStore

auth = MoixaCognitoAuth('you@example.com', 'yourpassword')
tokens = auth.login()
TokenStore().save(tokens)  # saves to ~/.moixa_tokens.json

client = MoixaClient(tokens)

site_users = client.get_site_users()
site_id = site_users[0]['siteId']
battery_id = next(d['id'] for d in site_users[0]['devices']
                  if d['deviceType'] == 'VirtualMoixaVictronSmartBattery')

print(client.get_current_battery_level())
print(client.get_device_current_operation_mode(battery_id))
```

## API methods

### Account

| Method | Description |
|---|---|
| `get_site_users()` | Sites and devices for the current user |
| `get_user_metadata()` | Account info: email, vendor, status |

### Readings

| Method | Description |
|---|---|
| `get_current_battery_level()` | Current battery SOC as a float (0.0-1.0) |
| `get_core_readings(site_id, time_range='latest')` | Power flow readings for a site (consumption, grid, solar, storage) |
| `get_device_status(device_id, time_range='latest')` | Per-device readings (consumption, grid, production, storage W, SOC) |
| `get_device(device_id)` | Full device info including attributes (capacity, hub, min SOC settings) |

### Battery control

| Method | Description |
|---|---|
| `get_device_current_operation_mode(device_id)` | Current mode and active plan |
| `set_device_operation_mode(device_id, mode)` | Switch mode: `'smart'`, `'schedule'`, or `'simple'` |
| `get_device_operation_schedule(device_id)` | Weekly 7-day charge/discharge schedule |
| `set_device_operation_schedule(device_id, plan)` | Replace the weekly schedule plan |

### History

| Method | Description |
|---|---|
| `get_device_intent_time_series(device_id, start, end)` | Planned charge/discharge intents over a date range |
| `get_device_tariff_time_series(device_id, start, end)` | Tariff prices over a date range (e.g. Octopus Agile) |

`start` and `end` are ISO 8601 strings, e.g. `'2026-05-10T00:00:00.000+01:00'`.

### Switching operation mode

```python
# Read current mode
mode = client.get_device_current_operation_mode(battery_id)['mode']

# Switch to schedule mode
client.set_device_operation_mode(battery_id, 'schedule')

# Edit and save the weekly schedule
schedule = client.get_device_operation_schedule(battery_id)
schedule['plan']['intents'][0]['intent']['socMin'] = 0.2
client.set_device_operation_schedule(battery_id, schedule['plan'])
```

## CLI

Requires tokens saved by `TokenStore` (default: `~/.moixa_tokens.json`).

```bash
moixa load                      # print saved token info
moixa sites                     # list site users and devices
moixa battery                   # show current battery level
moixa device <device_id>        # get device status
```

All commands accept `--token-file <path>` to use a non-default token file.

## Caveat

This is unofficial, based on static analysis of the Moixa app and captured browser traffic. The API may change without notice.
