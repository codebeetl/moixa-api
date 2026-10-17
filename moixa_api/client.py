
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import boto3
import requests
from aws_requests_auth.aws_auth import AWSRequestsAuth

from .auth import CognitoTokens, refresh_tokens
from .constants import AWS_REGION, COGNITO_IDENTITY_POOL_ID, COGNITO_USER_POOL_ID
from .exceptions import MoixaAuthError, MoixaError
from .schedule import build_intent, set_slot_lengths, slot_lengths, validate_plan
from .schedule_windows import ScheduleWindow, plan_to_windows, utc_offset_minutes, windows_to_plan


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
        """Replace the weekly schedule plan after validating it. Pass the full plan dict as returned by get_device_operation_schedule()."""
        validate_plan(plan)
        response = self._put(
            f'{self.api_url}/users/current/devices/{device_id}/operationModes/schedule',
            json={'plan': plan},
        )
        response.raise_for_status()

    # --- Schedule slot helpers (all read-modify-write via set_device_operation_schedule) ---

    _build_intent = staticmethod(build_intent)

    def get_schedule(self, device_id: str, tz: str = 'UTC', at: datetime | None = None) -> dict:
        """Return the raw 'plan' and the same schedule as readable 'windows' in time zone tz.
        The zone's UTC offset at `at` (default now) is used for the whole week."""
        plan = self.get_device_operation_schedule(device_id)['plan']
        return {'plan': plan, 'windows': plan_to_windows(plan, utc_offset_minutes(tz, at))}

    def set_schedule(self, device_id: str, windows: list[ScheduleWindow],
                     tz: str = 'UTC', at: datetime | None = None) -> None:
        """Replace the whole week with the given windows, whose times are in time zone tz.
        Time not covered by a window becomes 'balance'."""
        plan = self.get_device_operation_schedule(device_id)['plan']
        self.set_device_operation_schedule(
            device_id, windows_to_plan(windows, plan, utc_offset_minutes(tz, at))
        )

    def add_schedule_intent(self, device_id: str, kind: str, duration_minutes: int,
                             position: int = -1, soc_min: float = 0.1, soc_max: float = 1.0,
                             power_watts: float = None,
                             power_watts_min: float = None,
                             power_watts_max: float = None) -> None:
        """Insert a new intent slot. Time is stolen from the neighbouring slot.
        position=-1 appends to the end. Intent kinds: 'balance', 'charge/discharge', 'idle'."""
        schedule = self.get_device_operation_schedule(device_id)
        plan = schedule['plan']
        intents = plan['intents']
        lengths = slot_lengths(plan)
        if position == -1:
            position = len(intents)
        steal_idx = (position - 1) if position > 0 else 0
        if lengths[steal_idx] <= duration_minutes:
            raise MoixaError(
                f'Slot {steal_idx} only has {lengths[steal_idx]} min; '
                f'cannot steal {duration_minutes} min'
            )
        lengths[steal_idx] -= duration_minutes
        lengths.insert(position, duration_minutes)
        intents.insert(position, {
            'intent': self._build_intent(kind, soc_min, soc_max, power_watts, power_watts_min, power_watts_max),
        })
        set_slot_lengths(plan, lengths)
        self.set_device_operation_schedule(device_id, plan)

    def edit_schedule_intent(self, device_id: str, index: int,
                              kind: str = None, duration_minutes: int = None,
                              soc_min: float = None, soc_max: float = None,
                              power_watts: float = None,
                              power_watts_min: float = None,
                              power_watts_max: float = None) -> None:
        """Edit fields of an existing intent slot. Only supplied arguments are changed.
        If duration_minutes changes, the difference is absorbed by the neighbouring slot."""
        schedule = self.get_device_operation_schedule(device_id)
        plan = schedule['plan']
        lengths = slot_lengths(plan)
        if duration_minutes is not None and duration_minutes != lengths[index]:
            neighbour = (index - 1) if index > 0 else index + 1
            diff = duration_minutes - lengths[index]
            if lengths[neighbour] - diff < 1:
                raise MoixaError(f'Slot {neighbour} cannot absorb a {diff:+d} min duration change')
            lengths[neighbour] -= diff
            lengths[index] = duration_minutes
            set_slot_lengths(plan, lengths)
        intent = plan['intents'][index]['intent']
        for attr, val in [('kind', kind), ('socMin', soc_min), ('socMax', soc_max),
                          ('powerWatts', power_watts), ('powerWattsMin', power_watts_min),
                          ('powerWattsMax', power_watts_max)]:
            if val is not None:
                intent[attr] = val
        self.set_device_operation_schedule(device_id, plan)

    def delete_schedule_intent(self, device_id: str, index: int) -> None:
        """Remove an intent slot. Its duration is given to the neighbouring slot."""
        schedule = self.get_device_operation_schedule(device_id)
        plan = schedule['plan']
        intents = plan['intents']
        if len(intents) <= 1:
            raise MoixaError('Cannot delete the only schedule slot')
        lengths = slot_lengths(plan)
        intents.pop(index)
        removed_length = lengths.pop(index)
        lengths[(index - 1) if index > 0 else 0] += removed_length
        set_slot_lengths(plan, lengths)
        self.set_device_operation_schedule(device_id, plan)

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
