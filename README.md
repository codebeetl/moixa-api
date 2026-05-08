# moixa-py

Unofficial Python package for the Moixa GridShare platform, reconstructed from static analysis of the Android app.

## Features
- Cognito login via `USER_PASSWORD_AUTH`
- Token refresh and token-file persistence
- Selected REST API wrappers for devices, readings, commands, and sites
- CLI for login, refresh, site listing, and device lookup

## Install
```bash
pip install .
```

## CLI
```bash
moixa login --username you@example.com --password 'secret'
moixa sites
moixa device <device_uuid>
moixa refresh --username you@example.com
```

## Python
```python
from moixa_py import MoixaCognitoAuth, MoixaClient

auth = MoixaCognitoAuth('you@example.com', 'secret')
tokens = auth.login_password()
client = MoixaClient(tokens.access_token)
print(client.get_current_user_sites())
```

## Caveats
- This package is unofficial.
- The app bundle suggests Cognito auth, but the original mobile client may use `USER_SRP_AUTH` instead of plain `USER_PASSWORD_AUTH`.
- Some endpoint payloads were inferred and may need adjustment against live traffic.
