import json
import time
from pathlib import Path

import pytest

from moixa_py.auth import CognitoTokens, TokenStore, refresh_tokens
from moixa_py.exceptions import MoixaAuthError


TOKENS = CognitoTokens(
    access_token='acc',
    id_token='id',
    refresh_token='ref',
    expires_in=3600,
    token_type='Bearer',
    obtained_at=1000,
)


class TestCognitoTokens:
    def test_round_trip(self):
        assert CognitoTokens.from_dict(TOKENS.to_dict()) == TOKENS

    def test_to_dict_keys(self):
        d = TOKENS.to_dict()
        assert set(d) == {'access_token', 'id_token', 'refresh_token',
                          'expires_in', 'token_type', 'obtained_at'}

    def test_from_dict_optional_nones(self):
        t = CognitoTokens.from_dict({'access_token': 'x', 'id_token': None,
                                      'refresh_token': None, 'expires_in': None,
                                      'token_type': None, 'obtained_at': None})
        assert t.access_token == 'x'
        assert t.refresh_token is None


class TestTokenStore:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / 'tokens.json'
        store = TokenStore(str(path))
        store.save(TOKENS)
        loaded = store.load()
        assert loaded == TOKENS

    def test_save_writes_valid_json(self, tmp_path):
        path = tmp_path / 'tokens.json'
        TokenStore(str(path)).save(TOKENS)
        data = json.loads(path.read_text())
        assert data['access_token'] == 'acc'

    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(MoixaAuthError, match='not found'):
            TokenStore(str(tmp_path / 'missing.json')).load()


class TestRefreshTokens:
    def test_raises_without_refresh_token(self):
        t = CognitoTokens(access_token='a', id_token='i', refresh_token=None)
        with pytest.raises(MoixaAuthError, match='No refresh_token'):
            refresh_tokens(t)
