
from __future__ import annotations
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from pycognito import Cognito

from .constants import COGNITO_USER_POOL_ID, COGNITO_USER_POOL_CLIENT_ID
from .exceptions import MoixaAuthError


@dataclass
class CognitoTokens:
    access_token: str
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: Optional[str] = None
    obtained_at: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CognitoTokens':
        return cls(**data)


@dataclass
class User:
    tokens: CognitoTokens

    @classmethod
    def from_tokens(cls, tokens: CognitoTokens) -> 'User':
        return cls(tokens=tokens)


class TokenStore:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or os.path.expanduser('~/.moixa_tokens.json'))

    def save(self, tokens: CognitoTokens) -> None:
        self.path.write_text(json.dumps(tokens.to_dict(), indent=2))

    def load(self) -> CognitoTokens:
        if not self.path.exists():
            raise MoixaAuthError(f'token file not found: {self.path}')
        return CognitoTokens.from_dict(json.loads(self.path.read_text()))


def refresh_tokens(tokens: CognitoTokens) -> CognitoTokens:
    """Renew access+id tokens using a saved refresh_token."""
    if not tokens.refresh_token:
        raise MoixaAuthError('No refresh_token available')
    try:
        u = Cognito(
            COGNITO_USER_POOL_ID,
            COGNITO_USER_POOL_CLIENT_ID,
            id_token=tokens.id_token,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )
        u.renew_access_token()
    except Exception as exc:
        raise MoixaAuthError(f'Token refresh failed: {exc}') from exc
    return CognitoTokens(
        access_token=u.access_token,
        id_token=u.id_token or tokens.id_token,
        refresh_token=tokens.refresh_token,
        obtained_at=int(time.time()),
    )


class MoixaCognitoAuth:
    """Authenticates against the Moixa Cognito User Pool using SRP."""

    def __init__(
        self,
        username: str,
        password: str,
        user_pool_id: str = COGNITO_USER_POOL_ID,
        client_id: str = COGNITO_USER_POOL_CLIENT_ID,
    ):
        self.username = username
        self.password = password
        self.user_pool_id = user_pool_id
        self.client_id = client_id

    def login(self) -> CognitoTokens:
        try:
            u = Cognito(self.user_pool_id, self.client_id, username=self.username)
            u.authenticate(password=self.password)
        except Exception as exc:
            raise MoixaAuthError(f'Login failed: {exc}') from exc
        return CognitoTokens(
            access_token=u.access_token,
            id_token=u.id_token,
            refresh_token=u.refresh_token,
            obtained_at=int(time.time()),
        )
