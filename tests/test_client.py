from datetime import time
from unittest.mock import MagicMock, patch, call
import pytest

from moixa_py.auth import CognitoTokens
from moixa_py.client import MoixaClient
from moixa_py.exceptions import MoixaError
from moixa_py.schedule_windows import ScheduleWindow


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
    """Build a schedule dict with the given (kind, end offset in minutes) pairs."""
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

def ends(call_args):
    return [slot['durationMinutes'] for slot in call_args[0][1]['intents']]


class TestAddScheduleIntent:
    def test_add_at_position_1_steals_from_slot_0(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 800))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.add_schedule_intent('dev', kind='idle', duration_minutes=60, position=1)

        args = client.set_device_operation_schedule.call_args
        assert ends(args) == [440, 500, 800]
        assert args[0][1]['intents'][1]['intent']['kind'] == 'idle'

    def test_append_at_end(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 800))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.add_schedule_intent('dev', kind='idle', duration_minutes=100, position=-1)

        args = client.set_device_operation_schedule.call_args
        assert ends(args) == [500, 700, 800]
        assert args[0][1]['intents'][2]['intent']['kind'] == 'idle'

    def test_add_at_position_0_steals_from_slot_0(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 800))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.add_schedule_intent('dev', kind='idle', duration_minutes=60, position=0)

        args = client.set_device_operation_schedule.call_args
        assert ends(args) == [60, 500, 800]
        assert args[0][1]['intents'][0]['intent']['kind'] == 'idle'

    def test_raises_when_not_enough_time(self):
        client = make_client()
        schedule = make_schedule(('balance', 50), ('idle', 350))
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
        schedule = make_schedule(('balance', 500), ('idle', 800))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.edit_schedule_intent('dev', index=0, soc_min=0.2)

        args = client.set_device_operation_schedule.call_args
        assert args[0][1]['intents'][0]['intent']['socMin'] == 0.2
        assert ends(args) == [500, 800]

    def test_edit_duration_adjusts_neighbour(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 800))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.edit_schedule_intent('dev', index=0, duration_minutes=400)

        assert ends(client.set_device_operation_schedule.call_args) == [400, 800]

    def test_edit_duration_raises_when_neighbour_too_small(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 510))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        with pytest.raises(MoixaError, match='cannot absorb'):
            client.edit_schedule_intent('dev', index=0, duration_minutes=510)

    def test_no_change_when_no_args(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 800))
        original_schedule = make_schedule(('balance', 500), ('idle', 800))
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
        schedule = make_schedule(('balance', 500), ('idle', 600), ('balance', 900))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.delete_schedule_intent('dev', index=1)

        assert ends(client.set_device_operation_schedule.call_args) == [600, 900]

    def test_delete_first_slot_gives_time_to_new_first(self):
        client = make_client()
        schedule = make_schedule(('idle', 100), ('balance', 600))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.delete_schedule_intent('dev', index=0)

        assert ends(client.set_device_operation_schedule.call_args) == [600]

    def test_delete_last_slot_keeps_week_end(self):
        client = make_client()
        schedule = make_schedule(('balance', 500), ('idle', 800), ('balance', 1000))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        client.delete_schedule_intent('dev', index=2)

        assert ends(client.set_device_operation_schedule.call_args) == [500, 1000]

    def test_delete_only_slot_raises(self):
        client = make_client()
        schedule = make_schedule(('balance', 500))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)
        client.set_device_operation_schedule = MagicMock()

        with pytest.raises(MoixaError, match='only schedule slot'):
            client.delete_schedule_intent('dev', index=0)


# ---------------------------------------------------------------------------
# set_device_operation_schedule validation
# ---------------------------------------------------------------------------

def plan_with(*slots, **intent_overrides):
    plan = make_schedule(*slots)['plan']
    plan['intents'][0]['intent'].update(intent_overrides)
    return plan


class TestScheduleWindows:
    def test_set_schedule_writes_the_whole_week_in_one_put(self):
        client = make_client()
        client.get_device_operation_schedule = MagicMock(return_value=make_schedule(('balance', 10080)))
        client.set_device_operation_schedule = MagicMock()
        window = ScheduleWindow(time(0, 0), time(0, 0), 'charge/discharge', power_watts=3000, soc_max=1.0)

        client.set_schedule('dev', [window])

        client.set_device_operation_schedule.assert_called_once()
        plan = client.set_device_operation_schedule.call_args[0][1]
        assert [slot['durationMinutes'] for slot in plan['intents']] == [10080]
        assert plan['id'] == 'plan-1'

    def test_get_schedule_returns_plan_and_windows(self):
        client = make_client()
        schedule = make_schedule(('idle', 10080))
        client.get_device_operation_schedule = MagicMock(return_value=schedule)

        result = client.get_schedule('dev')

        assert result['plan'] == schedule['plan']
        assert len(result['windows']) == 7

    def test_restoring_a_saved_plan_uses_the_validated_put(self):
        client = make_client()
        client._put = MagicMock(return_value=mock_response({}))
        saved = make_schedule(('balance', 10080))['plan']

        client.set_device_operation_schedule('dev', saved)

        client._put.assert_called_once()


class TestSetDeviceOperationScheduleValidation:
    def test_valid_plan_is_sent(self):
        client = make_client()
        client._put = MagicMock(return_value=mock_response({}))

        client.set_device_operation_schedule('dev', plan_with(('balance', 500), ('idle', 10080)))

        client._put.assert_called_once()

    @pytest.mark.parametrize('plan', [
        {'periodDays': 7, 'intents': []},
        plan_with(('balance', 500), ('idle', 10081)),
        plan_with(('balance', 500), ('idle', 500)),
        plan_with(('balance', 500), ('idle', 400)),
        plan_with(('balance', 0), ('idle', 400)),
        plan_with(('turbo', 500)),
        plan_with(('charge/discharge', 500)),
        plan_with(('balance', 500), socMin=0.9, socMax=0.5),
    ])
    def test_invalid_plan_is_rejected_before_put(self, plan):
        client = make_client()
        client._put = MagicMock(return_value=mock_response({}))

        with pytest.raises(MoixaError):
            client.set_device_operation_schedule('dev', plan)

        client._put.assert_not_called()


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
