
from __future__ import annotations
import argparse
import json
import sys
from .auth import TokenStore
from .client import MoixaClient


def _print(data):
    print(json.dumps(data, indent=2) if isinstance(data, (dict, list)) else data)


def main() -> int:
    parser = argparse.ArgumentParser(prog='moixa', description='Moixa GridShare API client')
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_load = sub.add_parser('load', help='Show saved token info')
    p_load.add_argument('--token-file', default=None)

    p_sites = sub.add_parser('sites', help='List site users')
    p_sites.add_argument('--token-file', default=None)

    p_batt = sub.add_parser('battery', help='Show current battery level')
    p_batt.add_argument('--token-file', default=None)

    p_device = sub.add_parser('device', help='Get device status')
    p_device.add_argument('device_id')
    p_device.add_argument('--token-file', default=None)

    args = parser.parse_args()

    try:
        store = TokenStore(args.token_file)
        tokens = store.load()
        if args.cmd == 'load':
            _print(tokens.to_dict())
            return 0
        client = MoixaClient(tokens)
        if args.cmd == 'sites':
            _print(client.get_site_users())
            return 0
        if args.cmd == 'battery':
            _print({'battery_level': client.get_current_battery_level()})
            return 0
        if args.cmd == 'device':
            _print(client.get_device_status(args.device_id))
            return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 1
