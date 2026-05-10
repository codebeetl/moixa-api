
# moixa-py

Unofficial Python client for the Moixa GridShare API, rebuilt around the older client's model: Cognito User Pool tokens -> Cognito Identity Pool credentials -> SigV4-signed API requests.

## Usage
1. Create a `CognitoTokens` object with at least an `id_token`.
2. Build a `User` from those tokens.
3. Pass the user into `MoixaClient`.
4. Call API methods like `get_site_users()` or `get_current_battery_level()`.

## CLI
The CLI expects saved tokens in `~/.moixa_tokens.json` by default.

## Caveat
This version does not implement interactive login. It assumes you already have valid Cognito tokens from a separate auth flow.
