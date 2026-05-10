
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import boto3
import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth

from .auth import CognitoTokens, refresh_tokens
from .constants import AWS_REGION, COGNITO_IDENTITY_POOL_ID, COGNITO_USER_POOL_ID
from .exceptions import MoixaAuthError, MoixaError


@dataclass
class _AWSCredentials:
    access_key: str
    secret_key: str
    session_token: str


class MoixaClient:
    api_url = "https://api.mygridshare.com/prod/api/v1"

    def __init__(self, tokens: CognitoTokens):
        self._set_tokens(tokens)

    def _get_identity_credentials(self) -> _AWSCredentials:
        if not self.tokens.id_token:
            raise MoixaAuthError('id_token required for API authentication')
        logins = {
            f'cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}': self.tokens.id_token
        }
        identity_client = boto3.client('cognito-identity', region_name=AWS_REGION)
        id_resp = identity_client.get_id(
            IdentityPoolId=COGNITO_IDENTITY_POOL_ID, Logins=logins
        )
        creds_resp = identity_client.get_credentials_for_identity(
            IdentityId=id_resp['IdentityId'], Logins=logins
        )
        creds = creds_resp['Credentials']
        return _AWSCredentials(
            access_key=creds['AccessKeyId'],
            secret_key=creds['SecretKey'],
            session_token=creds['SessionToken'],
        )

    def _set_tokens(self, tokens: CognitoTokens) -> None:
        self.tokens = tokens
        creds = self._get_identity_credentials()
        self._auth = AWSRequestsAuth(
            aws_access_key=creds.access_key,
            aws_secret_access_key=creds.secret_key,
            aws_token=creds.session_token,
            aws_host='api.mygridshare.com',
            aws_region=AWS_REGION,
            aws_service='execute-api',
        )
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'aws-amplify/4.5.1 react-native',
            'idtoken': tokens.id_token or '',
            'Accept': 'application/json',
        })

    def _try_refresh(self) -> bool:
        if not self.tokens.refresh_token:
            return False
        try:
            self._set_tokens(refresh_tokens(self.tokens))
            return True
        except Exception:
            return False

    def _get(self, *args: Any, **kwargs: Any) -> requests.Response:
        res = self.session.get(*args, **kwargs, auth=self._auth, timeout=30)
        if res.status_code == 401 and self._try_refresh():
            res = self.session.get(*args, **kwargs, auth=self._auth, timeout=30)
        return res

    def _post(self, *args: Any, **kwargs: Any) -> requests.Response:
        res = self.session.post(*args, **kwargs, auth=self._auth, timeout=30)
        if res.status_code == 401 and self._try_refresh():
            res = self.session.post(*args, **kwargs, auth=self._auth, timeout=30)
        return res

    def _patch(self, *args: Any, **kwargs: Any) -> requests.Response:
        res = self.session.patch(*args, **kwargs, auth=self._auth, timeout=30)
        if res.status_code == 401 and self._try_refresh():
            res = self.session.patch(*args, **kwargs, auth=self._auth, timeout=30)
        return res

    def _put(self, *args: Any, **kwargs: Any) -> requests.Response:
        res = self.session.put(*args, **kwargs, auth=self._auth, timeout=30)
        if res.status_code == 401 and self._try_refresh():
            res = self.session.put(*args, **kwargs, auth=self._auth, timeout=30)
        return res

    def get_site_users(self):
        response = self._get(f'{self.api_url}/users/current/siteUsers')
        response.raise_for_status()
        return response.json()

    def get_user_metadata(self):
        response = self._get(f'{self.api_url}/users/current/metadata')
        response.raise_for_status()
        return response.json()

    def get_core_readings(self, site_id: str, time_range: str = 'latest',
                          roller: str = '', utc_offset: int = 60):
        params = {
            'roller': roller,
            'utcOffset': utc_offset,
            'extendedBounds': 'true',
            'timeRange': time_range,
            'select': (
                'core/consumption/in/AC/W,core/grid/in/AC/W,core/grid/out/AC/W,'
                'core/production/out/AC/W,core/storage/in/AC/W,core/storage/out/AC/W,'
                'derived/pc-delta/neg/W,derived/pc-delta/pos/W,'
                'derived/pcs-delta/neg/W,derived/pcs-delta/pos/W'
            ),
        }
        response = self._get(
            f'{self.api_url}/users/current/sites/{site_id}/coreReadingsV3',
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_device(self, device_id: str):
        response = self._get(f'{self.api_url}/users/current/devices/{device_id}')
        response.raise_for_status()
        return response.json()

    def get_device_status(self, device_id: str, time_range: str = 'latest'):
        channels = ['consumption/AC/W', 'grid/AC/W', 'production/AC/W',
                    'storage/AC/W', 'storage/SOC']
        params = [
            ('roller', '5m-avg'),
            *[('channels', c) for c in channels],
            ('timeRange', time_range),
            ('utcOffset', 0),
            ('extendedBounds', 'true'),
            ('select', ','.join(channels)),
        ]
        response = self._get(
            f'{self.api_url}/users/current/devices/{device_id}/specificReadings',
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def get_device_current_operation_mode(self, device_id: str):
        response = self._get(
            f'{self.api_url}/users/current/devices/{device_id}/currentOperationMode'
        )
        response.raise_for_status()
        return response.json()

    def get_device_operation_schedule(self, device_id: str):
        response = self._get(
            f'{self.api_url}/users/current/devices/{device_id}/operationModes/schedule'
        )
        response.raise_for_status()
        return response.json()

    def set_device_operation_mode(self, device_id: str, mode: str) -> None:
        """Switch mode: 'smart', 'schedule', or 'simple'."""
        response = self._patch(
            f'{self.api_url}/users/current/devices/{device_id}/currentOperationMode',
            json={'mode': mode},
        )
        response.raise_for_status()

    def set_device_operation_schedule(self, device_id: str, plan: dict) -> None:
        """Replace the weekly schedule plan. Pass the full plan dict as returned by get_device_operation_schedule()."""
        response = self._put(
            f'{self.api_url}/users/current/devices/{device_id}/operationModes/schedule',
            json={'plan': plan},
        )
        response.raise_for_status()

    # --- Schedule slot helpers (all read-modify-write via set_device_operation_schedule) ---

    @staticmethod
    def _build_intent(kind: str, soc_min: float, soc_max: float,
                      power_watts: float = None,
                      power_watts_min: float = None,
                      power_watts_max: float = None) -> dict:
        if kind not in ('balance', 'charge/discharge', 'idle'):
            raise MoixaError(f"Unknown intent kind {kind!r}. Use 'balance', 'charge/discharge', or 'idle'.")
        intent: dict = {'kind': kind, 'socMin': soc_min, 'socMax': soc_max}
        if kind == 'charge/discharge':
            if power_watts is None:
                raise MoixaError("power_watts is required for 'charge/discharge' intent")
            intent['powerWatts'] = power_watts
        elif kind == 'balance':
            intent['powerWattsMin'] = power_watts_min if power_watts_min is not None else -20
            intent['powerWattsMax'] = power_watts_max if power_watts_max is not None else 20
        return intent

    def add_schedule_intent(self, device_id: str, kind: str, duration_minutes: int,
                             position: int = -1, soc_min: float = 0.1, soc_max: float = 1.0,
                             power_watts: float = None,
                             power_watts_min: float = None,
                             power_watts_max: float = None) -> None:
        """Insert a new intent slot. Time is stolen from the neighbouring slot.
        position=-1 appends to the end. Intent kinds: 'balance', 'charge/discharge', 'idle'."""
        schedule = self.get_device_operation_schedule(device_id)
        intents = schedule['plan']['intents']
        if position == -1:
            position = len(intents)
        steal_idx = (position - 1) if position > 0 else 0
        if intents[steal_idx]['durationMinutes'] <= duration_minutes:
            raise MoixaError(
                f'Slot {steal_idx} only has {intents[steal_idx]["durationMinutes"]} min; '
                f'cannot steal {duration_minutes} min'
            )
        intents[steal_idx]['durationMinutes'] -= duration_minutes
        intents.insert(position, {
            'intent': self._build_intent(kind, soc_min, soc_max, power_watts, power_watts_min, power_watts_max),
            'durationMinutes': duration_minutes,
        })
        self.set_device_operation_schedule(device_id, schedule['plan'])

    def edit_schedule_intent(self, device_id: str, index: int,
                              kind: str = None, duration_minutes: int = None,
                              soc_min: float = None, soc_max: float = None,
                              power_watts: float = None,
                              power_watts_min: float = None,
                              power_watts_max: float = None) -> None:
        """Edit fields of an existing intent slot. Only supplied arguments are changed.
        If duration_minutes changes, the difference is absorbed by the neighbouring slot."""
        schedule = self.get_device_operation_schedule(device_id)
        intents = schedule['plan']['intents']
        slot = intents[index]
        if duration_minutes is not None and duration_minutes != slot['durationMinutes']:
            neighbour = (index - 1) if index > 0 else index + 1
            diff = duration_minutes - slot['durationMinutes']
            if intents[neighbour]['durationMinutes'] - diff < 1:
                raise MoixaError(f'Slot {neighbour} cannot absorb a {diff:+d} min duration change')
            intents[neighbour]['durationMinutes'] -= diff
            slot['durationMinutes'] = duration_minutes
        intent = slot['intent']
        for attr, val in [('kind', kind), ('socMin', soc_min), ('socMax', soc_max),
                          ('powerWatts', power_watts), ('powerWattsMin', power_watts_min),
                          ('powerWattsMax', power_watts_max)]:
            if val is not None:
                intent[attr] = val
        self.set_device_operation_schedule(device_id, schedule['plan'])

    def delete_schedule_intent(self, device_id: str, index: int) -> None:
        """Remove an intent slot. Its duration is given to the neighbouring slot."""
        schedule = self.get_device_operation_schedule(device_id)
        intents = schedule['plan']['intents']
        if len(intents) <= 1:
            raise MoixaError('Cannot delete the only schedule slot')
        removed = intents.pop(index)
        neighbour = (index - 1) if index > 0 else 0
        intents[neighbour]['durationMinutes'] += removed['durationMinutes']
        self.set_device_operation_schedule(device_id, schedule['plan'])

    @staticmethod
    def parse_jts(data: dict) -> list:
        """Flatten a JTS time series response into a list of dicts.

        Each dict has a 'ts' key (ISO 8601 timestamp) and one key per column
        named after the column's 'name' field. Missing values are None.

        Works with any JTS response: get_site_forecasts, get_core_readings,
        get_device_status, etc.

        Example:
            forecasts = client.get_site_forecasts(site_id, start, end)
            for row in client.parse_jts(forecasts):
                print(row['ts'], row['consumption_W'], row['production_W'])
        """
        cols = {k: v['name'] for k, v in data['header']['columns'].items()}
        result = []
        for record in data['data']:
            row = {'ts': record['ts']}
            for col_id, name in cols.items():
                row[name] = record.get('f', {}).get(col_id, {}).get('v')
            result.append(row)
        return result

    def get_site_forecasts(self, site_id: str, time_range_start: str, time_range_end: str,
                           select: str = 'consumption_W,production_W'):
        """Predicted consumption and solar production for a site over a time range.
        time_range_start/end are ISO 8601 strings, e.g. '2026-05-10T00:00:00.000Z'."""
        response = self._get(
            f'{self.api_url}/users/current/sites/{site_id}/forecasts',
            params={'select': select, 'timeRange': f'{time_range_start},{time_range_end}'},
        )
        response.raise_for_status()
        return response.json()

    def get_flex_dispatches(self):
        """Flex dispatch events for the current user."""
        response = self._get(f'{self.api_url}/users/current/flexDispatches')
        response.raise_for_status()
        return response.json()

    def get_device_intent_time_series(self, device_id: str, interval_start: str, interval_end: str):
        response = self._get(
            f'{self.api_url}/users/current/devices/{device_id}/intentTimeSeries',
            params={'interval': f'{interval_start},{interval_end}'},
        )
        response.raise_for_status()
        return response.json()

    def get_device_tariff_time_series(self, device_id: str, interval_start: str, interval_end: str):
        response = self._get(
            f'{self.api_url}/users/current/devices/{device_id}/tariffTimeSeries',
            params={'interval': f'{interval_start},{interval_end}'},
        )
        response.raise_for_status()
        return response.json()

    def get_current_battery_level(self) -> float:
        if not getattr(self, 'known_site_users', None):
            self.known_site_users = self.get_site_users()
        battery_device_id = ''
        for device in self.known_site_users[0]['devices']:
            if device['deviceType'] == 'VirtualMoixaVictronSmartBattery':
                battery_device_id = device['id']
                break
        if not battery_device_id:
            raise MoixaError('No battery device found')
        status_data = self.get_device_status(battery_device_id)
        for col_data in status_data.get('data', [{}])[0].get('f', {}).values():
            pass
        soc_col = next(
            (k for k, v in status_data['header']['columns'].items() if v['id'] == 'storage/SOC'),
            None,
        ) if status_data.get('header') else None
        if soc_col:
            return float(status_data['data'][0]['f'][soc_col]['v'])
        return float(status_data.get('data', [{}])[0].get('f', {}).get('1', {}).get('v', -1))
