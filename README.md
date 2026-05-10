# moixa-py

Unofficial Python client for the Moixa GridShare API, reverse-engineered from the Android app. Authenticates using Cognito User Pool SRP, exchanges tokens for temporary AWS credentials via the Cognito Identity Pool, and signs API requests with SigV4, matching the mobile app's auth flow exactly.

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
print(client.get_site_users())
print(client.get_current_battery_level())
```

## API methods

| Method | Description |
|---|---|
| `get_site_users()` | List sites and devices for the current user |
| `get_current_battery_level()` | Current battery SOC as a float |
| `get_core_readings(site_id)` | Latest power flow readings for a site |
| `get_device_status(device_id)` | Latest readings for a specific device |

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

This is unofficial and based on static analysis of the Moixa app. The API may change without notice.
