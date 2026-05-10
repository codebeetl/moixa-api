from unittest.mock import MagicMock, patch, call
import pytest

from moixa_py.auth import CognitoTokens
from moixa_py.client import MoixaClient
from moixa_py.exceptions import MoixaError


FAKE_TOKENS = CognitoTokens(
    access_token='acc',
    id_token='id-token',
    refresh_token='ref',
)

FAKE_CREDS = MagicMock(access_key='AKID', secret_key='SECRET', session_token='TOKEN')


def make_client():
    with patch.object(MoixaClient, '_get_identity_credentials', return_value=FAKE_CREDS):
        return MoixaClient(FAKE_TOKENS)


def mock_response(data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data
    r.raise_for_status = MagicMock()
    return r


def make_schedule(*slots):
    """Build a schedule dict with the given (kind, duration) pairs."""
    intents = [
        {'intent': {'kind': kind, 'socMin': 0.1, 'socMax': 1.0}, 'durationMinutes': dur}
        for kind, dur in slots
    ]
    return {'plan': {'periodDays': 7, 'id': 'plan-1', 'intents': intents}}


# ---------------------------------------------------------------------------
# _build_intent
# ---------------------------------------------------------------------------

class TestBuildIntent:
    def test_balance(self):
        i = MoixaClient._build_intent('balance', 0.1, 1.0)
        assert i == {'kind': 'balance', 'socMin': 0.1, 'socMax': 1.0,
                     'powerWattsMin': -20, 'powerWattsMax': 20}

    def test_balance_custom_power(self):
        i = MoixaClient._build_intent('balance', 0.1, 1.0, power_watts_min=-500, power_watts_max=500)
        assert i['powerWattsMin'] == -500
        assert i['powerWattsMax'] == 500

    def test_charge_discharge(self):
        i = MoixaClient._build_intent('charge/discharge', 0.1, 0.8, power_watts=2000)
        assert i == {'kind': 'charge/discharge', 'socMin': 0.1, 'socMax': 0.8, 'powerWatts': 2000}

    def test_charge_discharge_requires_power_watts(self):
        with pytest.raises(MoixaError, match='power_watts is required'):
            MoixaClient._build_intent('charge/discharge', 0.1, 1.0)

    def test_idle(self):
        i = MoixaClient._build_intent('idle', 0.2, 0.9)
        assert i == {'kind': 'idle', 'socMin': 0.2, 'socMax': 0.9}

    def test_unknown_kind(self):
        with pytest.raises(MoixaError, match="Unknown intent kind"):
            MoixaClient._build_intent('turbo', 0.1, 1.0)


# ---------------------------------------------------------------------------
# add_schedule_intent
# ---------------------------------------------------------------------------

class TestAddScheduleIntent:
    def test_add_at_position_1_steals_from_slot_0(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.add_schedule_intent('dev', kind='idle', duration_minutes=60, position=1)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert len(intents) == 3
        assert intents[0]['durationMinutes'] == 440  # 500 - 60
        assert intents[1]['intent']['kind'] == 'idle'
        assert intents[1]['durationMinutes'] == 60
        assert intents[2]['durationMinutes'] == 300  # unchanged

    def test_append_at_end(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.add_schedule_intent('dev', kind='idle', duration_minutes=100, position=-1)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert len(intents) == 3
        assert intents[2]['intent']['kind'] == 'idle'
        assert intents[1]['durationMinutes'] == 200  # 300 - 100 stolen

    def test_add_at_position_0_steals_from_slot_0(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.add_schedule_intent('dev', kind='idle', duration_minutes=60, position=0)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert intents[0]['intent']['kind'] == 'idle'
        assert intents[1]['durationMinutes'] == 440  # 500 - 60

    def test_raises_when_not_enough_time(self):
        client = make_client()
        schedule = make_schedule(('balance', 50), ('idle', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        with pytest.raises(MoixaError, match='cannot steal'):
            client.add_schedule_intent('dev', kind='idle', duration_minutes=100, position=1)


# ---------------------------------------------------------------------------
# edit_schedule_intent
# ---------------------------------------------------------------------------

class TestEditScheduleIntent:
    def test_edit_soc_min(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.edit_schedule_intent('dev', index=0, soc_min=0.2)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert intents[0]['intent']['socMin'] == 0.2
        assert intents[0]['durationMinutes'] == 500  # unchanged

    def test_edit_duration_adjusts_neighbour(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.edit_schedule_intent('dev', index=0, duration_minutes=400)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert intents[0]['durationMinutes'] == 400
        assert intents[1]['durationMinutes'] == 400  # gained 100

    def test_edit_duration_raises_when_neighbour_too_small(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 10))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        with pytest.raises(MoixaError, match='cannot absorb'):
            client.edit_schedule_intent('dev', index=0, duration_minutes=510)

    def test_no_change_when_no_args(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 300))
        original_schedule = make_schedule(('balance', 500), ('idle', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.edit_schedule_intent('dev', index=0)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert intents[0] == original_schedule['plan']['intents'][0]


# ---------------------------------------------------------------------------
# delete_schedule_intent
# ---------------------------------------------------------------------------

class TestDeleteScheduleIntent:
    def test_delete_middle_slot(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 100), ('balance', 300))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.delete_schedule_intent('dev', index=1)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert len(intents) == 2
        assert intents[0]['durationMinutes'] == 600  # 500 + 100
        assert intents[1]['durationMinutes'] == 300

    def test_delete_first_slot_gives_time_to_new_first(self):
        client = make_client()
        schedule = make_schedule(('idle', 100), ('balance', 500))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.delete_schedule_intent('dev', index=0)

        intents = client.set_device_operation_schedule.call_args[0][1]['intents']
        assert len(intents) == 1
        assert intents[0]['durationMinutes'] == 600  # 500 + 100

    def test_delete_only_slot_raises(self):
        client = make_client()
        schedule = make_schedule(('balance', 500))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        with pytest.raises(MoixaError, match='only schedule slot'):
            client.delete_schedule_intent('dev', index=0)


# ---------------------------------------------------------------------------
# parse_jts
# ---------------------------------------------------------------------------

class TestParseJts:
    def _make_jts(self, cols, records):
        return {
            'header': {'columns': {str(i): {'name': n} for i, n in enumerate(cols)}},
            'data': records,
        }

    def test_flattens_columns(self):
        data = self._make_jts(
            ['consumption_W', 'production_W'],
            [{'ts': '2026-05-11T10:00:00.000Z', 'f': {'0': {'v': 500.0}, '1': {'v': 1200.0}}}],
        )
        rows = MoixaClient.parse_jts(data)
        assert len(rows) == 1
        assert rows[0] == {'ts': '2026-05-11T10:00:00.000Z', 'consumption_W': 500.0, 'production_W': 1200.0}

    def test_missing_value_is_none(self):
        data = self._make_jts(
            ['consumption_W', 'production_W'],
            [{'ts': '2026-05-11T00:00:00.000Z', 'f': {'0': {'v': 300.0}}}],
        )
        rows = MoixaClient.parse_jts(data)
        assert rows[0]['production_W'] is None

    def test_multiple_records(self):
        data = self._make_jts(
            ['val'],
            [
                {'ts': '2026-05-11T00:00:00.000Z', 'f': {'0': {'v': 1.0}}},
                {'ts': '2026-05-11T00:30:00.000Z', 'f': {'0': {'v': 2.0}}},
            ],
        )
        rows = MoixaClient.parse_jts(data)
        assert len(rows) == 2
        assert rows[1]['val'] == 2.0

    def test_importable_as_top_level(self):
        from moixa_py import parse_jts
        assert callable(parse_jts)


# ---------------------------------------------------------------------------
# get_current_battery_level
# ---------------------------------------------------------------------------

class TestGetCurrentBatteryLevel:
    def test_finds_soc_by_column_name(self):
        client = make_client()
        client.known_site_users = [{'devices': [
            {'deviceType': 'VirtualMoixaVictronSmartBattery', 'id': 'bat-1'}
        ]}]
        status_data = {
            'header': {'columns': {
                '0': {'id': 'consumption/AC/W'},
                '1': {'id': 'storage/SOC'},
            }},
            'data': [{'f': {'0': {'v': 500.0}, '1': {'v': 0.73}}}],
        }
        client.get_device_status = MagicMock(return_value=status_data)

        assert client.get_current_battery_level() == pytest.approx(0.73)

    def test_raises_when_no_battery_device(self):
        client = make_client()
        client.known_site_users = [{'devices': [
            {'deviceType': 'VirtualMoixaGridShareHub', 'id': 'hub-1'}
        ]}]
        with pytest.raises(MoixaError, match='No battery device'):
            client.get_current_battery_level()
