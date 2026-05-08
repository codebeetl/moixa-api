from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .constants import AWS_REGION, COGNITO_IDP_ENDPOINT, COGNITO_USER_POOL_CLIENT_ID
from .exceptions import MoixaAuthError


def _aws_headers(target: str) -> Dict[str, str]:
    return {
        'Content-Type': 'application/x-amz-json-1.1',
        'X-Amz-Target': target,
    }


def _secret_hash(username: str, client_id: str, client_secret: str) -> str:
    digest = hmac.new(client_secret.encode(), (username + client_id).encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


@dataclass
class CognitoTokens:
    access_token: str
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: Optional[str] = None
    obtained_at: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['obtained_at'] = data.get('obtained_at') or int(time.time())
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CognitoTokens':
        return cls(**data)


class TokenStore:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or os.path.expanduser('~/.moixa_tokens.json'))

    def save(self, tokens: CognitoTokens) -> None:
        self.path.write_text(json.dumps(tokens.to_dict(), indent=2))

    def load(self) -> CognitoTokens:
        if not self.path.exists():
            raise MoixaAuthError(f'token file not found: {self.path}')
        return CognitoTokens.from_dict(json.loads(self.path.read_text()))


class MoixaCognitoAuth:
    def __init__(self, username: str, password: Optional[str] = None, client_id: str = COGNITO_USER_POOL_CLIENT_ID,
                 region: str = AWS_REGION, client_secret: Optional[str] = None, session: Optional[requests.Session] = None):
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.region = region
        self.endpoint = COGNITO_IDP_ENDPOINT.replace(AWS_REGION, region)
        self.session = session or requests.Session()

    def _auth_parameters(self, auth_flow: str, refresh_token: Optional[str] = None) -> Dict[str, str]:
        params = {'USERNAME': self.username}
        if auth_flow == 'USER_PASSWORD_AUTH':
            if not self.password:
                raise MoixaAuthError('password required for USER_PASSWORD_AUTH')
            params['PASSWORD'] = self.password
        elif auth_flow == 'REFRESH_TOKEN_AUTH':
            if not refresh_token:
                raise MoixaAuthError('refresh token required for REFRESH_TOKEN_AUTH')
            params['REFRESH_TOKEN'] = refresh_token
        elif auth_flow == 'USER_SRP_AUTH':
            raise MoixaAuthError('USER_SRP_AUTH not yet implemented in this package')
        if self.client_secret:
            params['SECRET_HASH'] = _secret_hash(self.username, self.client_id, self.client_secret)
        return params

    def initiate_auth(self, auth_flow: str = 'USER_PASSWORD_AUTH', refresh_token: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            'AuthFlow': auth_flow,
            'ClientId': self.client_id,
            'AuthParameters': self._auth_parameters(auth_flow, refresh_token=refresh_token),
        }
        resp = self.session.post(self.endpoint, headers=_aws_headers('AWSCognitoIdentityProviderService.InitiateAuth'), json=payload, timeout=30)
        if not resp.ok:
            raise MoixaAuthError(f'{resp.status_code} {resp.text}')
        return resp.json()

    def login_password(self) -> CognitoTokens:
        data = self.initiate_auth('USER_PASSWORD_AUTH')
        result = data.get('AuthenticationResult')
        if not result:
            raise MoixaAuthError(f'Expected AuthenticationResult, got: {json.dumps(data)}')
        return CognitoTokens(
            access_token=result.get('AccessToken'),
            id_token=result.get('IdToken'),
            refresh_token=result.get('RefreshToken'),
            expires_in=result.get('ExpiresIn'),
            token_type=result.get('TokenType'),
            obtained_at=int(time.time()),
        )

    def refresh(self, refresh_token: str) -> CognitoTokens:
        data = self.initiate_auth('REFRESH_TOKEN_AUTH', refresh_token=refresh_token)
        result = data.get('AuthenticationResult')
        if not result:
            raise MoixaAuthError(f'Expected AuthenticationResult, got: {json.dumps(data)}')
        return CognitoTokens(
            access_token=result.get('AccessToken'),
            id_token=result.get('IdToken'),
            refresh_token=refresh_token,
            expires_in=result.get('ExpiresIn'),
            token_type=result.get('TokenType'),
            obtained_at=int(time.time()),
        )

    def forgot_password(self) -> Dict[str, Any]:
        payload = {'ClientId': self.client_id, 'Username': self.username}
        if self.client_secret:
            payload['SecretHash'] = _secret_hash(self.username, self.client_id, self.client_secret)
        resp = self.session.post(self.endpoint, headers=_aws_headers('AWSCognitoIdentityProviderService.ForgotPassword'), json=payload, timeout=30)
        if not resp.ok:
            raise MoixaAuthError(f'{resp.status_code} {resp.text}')
        return resp.json()

    def confirm_forgot_password(self, confirmation_code: str, new_password: str) -> Dict[str, Any]:
        payload = {
            'ClientId': self.client_id,
            'Username': self.username,
            'ConfirmationCode': confirmation_code,
            'Password': new_password,
        }
        if self.client_secret:
            payload['SecretHash'] = _secret_hash(self.username, self.client_id, self.client_secret)
        resp = self.session.post(self.endpoint, headers=_aws_headers('AWSCognitoIdentityProviderService.ConfirmForgotPassword'), json=payload, timeout=30)
        if not resp.ok:
            raise MoixaAuthError(f'{resp.status_code} {resp.text}')
        return resp.json() if resp.text else {'ok': True}
