
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

    def get_site_users(self):
        response = self._get(f'{self.api_url}/users/current/siteUsers')
        response.raise_for_status()
        return response.json()

    def get_current_user_sites(self):
        response = self._get(f'{self.api_url}/users/current/sites')
        response.raise_for_status()
        return response.json()

    def get_core_readings(self, site_id: str):
        response = self._get(
            f'{self.api_url}/users/current/sites/{site_id}/coreReadingsV3'
            '?roller=&utcOffset=60&extendedBounds=true&timeRange=latest'
            '&select=core%2Fconsumption%2Fin%2FAC%2FW%2Ccore%2Fgrid%2Fin%2FAC%2FW'
            '%2Ccore%2Fgrid%2Fout%2FAC%2FW%2Ccore%2Fproduction%2Fout%2FAC%2FW'
            '%2Ccore%2Fstorage%2Fin%2FAC%2FW%2Ccore%2Fstorage%2Fout%2FAC%2FW'
            '%2Cderived%2Fpc-delta%2Fneg%2FW%2Cderived%2Fpc-delta%2Fpos%2FW'
            '%2Cderived%2Fpcs-delta%2Fneg%2FW%2Cderived%2Fpcs-delta%2Fpos%2FW'
        )
        response.raise_for_status()
        return response.json()

    def get_device_status(self, device_id: str):
        response = self._get(
            f'{self.api_url}/users/current/devices/{device_id}/specificReadings'
            '?channels=storage%2FSOC&timeRange=latest&roller=5m-avg'
            '&extendedBounds=false&utcOffset=60'
            '&select=storage%2FAC%2FW%2Cstorage%2FSOC'
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
        return float(status_data.get('data', [{}])[0].get('f', {}).get('1', {}).get('v', -1))
