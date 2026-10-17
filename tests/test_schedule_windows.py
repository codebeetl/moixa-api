from datetime import datetime, time, timezone

import pytest

from moixa_api.exceptions import MoixaError
from moixa_api.schedule import validate_plan
from moixa_api.schedule_windows import (
    ScheduleWindow,
    plan_to_windows,
    utc_offset_minutes,
    windows_to_plan,
)

BASE_PLAN = {'periodDays': 7, 'id': 'plan-1', 'intents': []}
WEEK = 7 * 1440


def charge(start, end, **kwargs):
    return ScheduleWindow(start=start, end=end, kind='charge/discharge', power_watts=3000, **kwargs)


def ends_and_kinds(plan):
    return [(slot['durationMinutes'], slot['intent']['kind']) for slot in plan['intents']]


class TestWindowsToPlan:
    def test_all_day_every_day_is_one_slot(self):
        plan = windows_to_plan([charge(time(0, 0), time(0, 0))], BASE_PLAN)

        assert ends_and_kinds(plan) == [(WEEK, 'charge/discharge')]
        assert plan['id'] == 'plan-1'

    def test_gaps_become_balance(self):
        plan = windows_to_plan([charge(time(8, 0), time(10, 0), days=(0,))], BASE_PLAN)

        assert ends_and_kinds(plan) == [
            (480, 'balance'), (600, 'charge/discharge'), (WEEK, 'balance'),
        ]

    def test_every_day_window_repeats_daily(self):
        plan = windows_to_plan([charge(time(1, 0), time(3, 0))], BASE_PLAN)

        charge_ends = [end for end, kind in ends_and_kinds(plan) if kind == 'charge/discharge']
        assert charge_ends == [180 + day * 1440 for day in range(7)]

    def test_window_past_midnight_wraps_the_week(self):
        plan = windows_to_plan([charge(time(23, 0), time(1, 0), days=(6,))], BASE_PLAN)

        assert ends_and_kinds(plan) == [
            (60, 'charge/discharge'), (WEEK - 60, 'balance'), (WEEK, 'charge/discharge'),
        ]

    def test_utc_offset_shifts_local_times_earlier(self):
        plan = windows_to_plan([charge(time(2, 0), time(4, 0), days=(0,))], BASE_PLAN, utc_offset=60)

        assert ends_and_kinds(plan) == [
            (60, 'balance'), (180, 'charge/discharge'), (WEEK, 'balance'),
        ]

    def test_overlapping_windows_raise(self):
        with pytest.raises(MoixaError, match='overlap'):
            windows_to_plan([
                charge(time(8, 0), time(10, 0), days=(0,)),
                charge(time(9, 0), time(11, 0), days=(0,)),
            ], BASE_PLAN)

    def test_result_is_a_valid_plan(self):
        plan = windows_to_plan([charge(time(23, 0), time(1, 0))], BASE_PLAN, utc_offset=-300)

        validate_plan(plan)


class TestPlanToWindows:
    @pytest.mark.parametrize('utc_offset', [0, 60, -300])
    def test_round_trip_restores_the_plan(self, utc_offset):
        original = windows_to_plan([
            charge(time(23, 0), time(2, 0)),
            ScheduleWindow(time(12, 0), time(14, 30), 'idle', days=(2, 4), soc_min=0.2),
        ], BASE_PLAN, utc_offset)

        restored = windows_to_plan(plan_to_windows(original, utc_offset), BASE_PLAN, utc_offset)

        assert restored == original

    def test_windows_are_split_at_local_midnight_and_sorted(self):
        plan = windows_to_plan([charge(time(0, 0), time(0, 0))], BASE_PLAN)

        windows = plan_to_windows(plan)

        assert [window.days for window in windows] == [(day,) for day in range(7)]
        assert all(window.start == time(0, 0) and window.end == time(0, 0) for window in windows)

    def test_unfinished_week_is_filled_with_balance(self):
        plan = {'periodDays': 7, 'intents': [
            {'intent': {'kind': 'idle', 'socMin': 0.1, 'socMax': 1.0}, 'durationMinutes': 10019},
        ]}

        windows = plan_to_windows(plan)

        assert windows[-1].kind == 'balance'
        assert windows[-1].days == (6,)


class TestUtcOffsetMinutes:
    def test_follows_clock_changes(self):
        summer = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
        winter = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)

        assert utc_offset_minutes('Europe/London', summer) == 60
        assert utc_offset_minutes('Europe/London', winter) == 0

    def test_utc_is_zero(self):
        assert utc_offset_minutes('UTC') == 0

    def test_unknown_zone_raises(self):
        with pytest.raises(MoixaError, match='Unknown time zone'):
            utc_offset_minutes('Mars/Olympus')
