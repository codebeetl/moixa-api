from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from .constants import BASE_URL
from .exceptions import MoixaError


@dataclass
class MoixaClient:
    access_token: Optional[str] = None
    base_url: str = BASE_URL
    timeout: int = 30
    session: Optional[requests.Session] = None

    def __post_init__(self):
        if self.session is None:
            self.session = requests.Session()

    def _headers(self) -> Dict[str, str]:
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        if self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = self.base_url.rstrip('/') + path
        resp = self.session.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        if not resp.ok:
            raise MoixaError(f'{resp.status_code} {resp.text}')
        ctype = resp.headers.get('content-type', '')
        return resp.json() if 'json' in ctype else resp.text

    def get_current_user_sites(self):
        return self.request('GET', '/api/v1/users/current/sites')

    def get_users_current_site_users(self):
        return self.request('GET', '/api/v1/users/current/siteUsersV1')

    def get_device(self, device_uuid: str):
        return self.request('GET', f'/api/v1/devices/{device_uuid}')

    def get_device_readings(self, device_uuid: str, **params: Any):
        return self.request('GET', f'/api/v1/devices/{device_uuid}/readings', params=params)

    def get_device_core_readings(self, device_uuid: str, **params: Any):
        return self.request('GET', f'/api/v1/devices/{device_uuid}/coreReadings', params=params)

    def get_device_iot_read_credentials(self, device_uuid: str):
        return self.request('GET', f'/api/v1/devices/{device_uuid}/iotReadCredentials')

    def post_device_command(self, device_uuid: str, payload: Dict[str, Any]):
        return self.request('POST', f'/api/v1/devices/{device_uuid}/commands', json=payload)

    def get_device_overlay_plan(self, device_uuid: str):
        return self.request('GET', f'/api/v1/devices/{device_uuid}/overlayPlan')

    def get_device_overlay_plan_history(self, device_uuid: str, **params: Any):
        return self.request('GET', f'/api/v1/devices/{device_uuid}/overlayPlanHistory', params=params)

    def get_device_accepted_plan_timeseries(self, device_uuid: str, **params: Any):
        return self.request('GET', f'/api/v1/devices/{device_uuid}/acceptedPlanTimeseries', params=params)

    def update_device_periodical_plan(self, device_uuid: str, payload: Dict[str, Any]):
        return self.request('PUT', f'/api/v1/devices/{device_uuid}/periodicalPlan', json=payload)

    def get_user(self, user_uuid: str):
        return self.request('GET', f'/api/v1/users/{user_uuid}')

    def get_user_devices(self, user_uuid: str):
        return self.request('GET', f'/api/v1/users/{user_uuid}/devices')

    def get_user_device(self, user_uuid: str, device_uuid: str):
        return self.request('GET', f'/api/v1/users/{user_uuid}/devices/{device_uuid}')

    def get_user_device_readings(self, user_uuid: str, device_uuid: str, **params: Any):
        return self.request('GET', f'/api/v1/users/{user_uuid}/devices/{device_uuid}/readings', params=params)

    def get_user_device_iot_read_credentials(self, user_uuid: str, device_uuid: str):
        return self.request('GET', f'/api/v1/users/{user_uuid}/devices/{device_uuid}/iotReadCredentials')

    def post_user_device_command(self, user_uuid: str, device_uuid: str, payload: Dict[str, Any]):
        return self.request('POST', f'/api/v1/users/{user_uuid}/devices/{device_uuid}/commands', json=payload)

    def get_user_flex_events(self, user_uuid: str, **params: Any):
        return self.request('GET', f'/api/v1/users/{user_uuid}/flexEvents', params=params)
