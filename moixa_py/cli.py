from __future__ import annotations
import argparse
import json
import sys

from .auth import MoixaCognitoAuth, TokenStore
from .client import MoixaClient
from .exceptions import MoixaError


def _print(data):
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2))
    else:
        print(data)


def main() -> int:
    parser = argparse.ArgumentParser(prog='moixa', description='Unofficial Moixa GridShare CLI')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_login = sub.add_parser('login', help='Authenticate with Cognito using USER_PASSWORD_AUTH')
    p_login.add_argument('--username', required=True)
    p_login.add_argument('--password', required=True)
    p_login.add_argument('--token-file', default=None)

    p_refresh = sub.add_parser('refresh', help='Refresh an access token using a saved refresh token')
    p_refresh.add_argument('--username', required=True)
    p_refresh.add_argument('--token-file', default=None)

    p_sites = sub.add_parser('sites', help='List current user sites')
    p_sites.add_argument('--token-file', default=None)

    p_device = sub.add_parser('device', help='Get a device by UUID')
    p_device.add_argument('device_uuid')
    p_device.add_argument('--token-file', default=None)

    args = parser.parse_args()

    try:
        if args.cmd == 'login':
            auth = MoixaCognitoAuth(args.username, args.password)
            tokens = auth.login_password()
            TokenStore(args.token_file).save(tokens)
            _print(tokens.to_dict())
            return 0

        if args.cmd == 'refresh':
            store = TokenStore(args.token_file)
            tokens = store.load()
            auth = MoixaCognitoAuth(args.username)
            new_tokens = auth.refresh(tokens.refresh_token)
            store.save(new_tokens)
            _print(new_tokens.to_dict())
            return 0

        if args.cmd in {'sites', 'device'}:
            tokens = TokenStore(args.token_file).load()
            client = MoixaClient(tokens.access_token)
            if args.cmd == 'sites':
                _print(client.get_current_user_sites())
            elif args.cmd == 'device':
                _print(client.get_device(args.device_uuid))
            return 0
    except MoixaError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 1


if __name__ == '__main__':
    raise SystemExit(main())
