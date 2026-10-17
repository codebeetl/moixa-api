from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .exceptions import MoixaError
from .schedule import DEFAULT_PERIOD_DAYS, MINUTES_PER_DAY, build_intent

ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)
DEFAULT_SOC_MIN = 0.1
DEFAULT_SOC_MAX = 1.0


@dataclass(frozen=True)
class ScheduleWindow:
    """A time range on the given weekdays (0 = Monday) with the behaviour to apply.

    `end` of 00:00 means the end of the day. An `end` at or before `start` runs past midnight.
    """

    start: time
    end: time
    kind: str
    days: tuple[int, ...] = ALL_DAYS
    soc_min: float = DEFAULT_SOC_MIN
    soc_max: float = DEFAULT_SOC_MAX
    power_watts: float | None = None
    power_watts_min: float | None = None
    power_watts_max: float | None = None

    def intent(self) -> dict:
        """Return the plan intent for this window."""
        return build_intent(self.kind, self.soc_min, self.soc_max,
                            self.power_watts, self.power_watts_min, self.power_watts_max)

    @classmethod
    def from_intent(cls, start: time, end: time, day: int, intent: dict) -> ScheduleWindow:
        """Build a single-day window from a plan intent."""
        return cls(start=start, end=end, kind=intent['kind'], days=(day,),
                   soc_min=intent['socMin'], soc_max=intent['socMax'],
                   power_watts=intent.get('powerWatts'),
                   power_watts_min=intent.get('powerWattsMin'),
                   power_watts_max=intent.get('powerWattsMax'))


def utc_offset_minutes(tz: str, at: datetime | None = None) -> int:
    """Return the UTC offset in minutes of IANA time zone tz at `at` (default now)."""
    try:
        zone = ZoneInfo(tz)
    except ZoneInfoNotFoundError as error:
        raise MoixaError(f'Unknown time zone {tz!r}') from error
    moment = (at or datetime.now(timezone.utc)).astimezone(zone)
    return int(moment.utcoffset().total_seconds() // 60)


def windows_to_plan(windows: list[ScheduleWindow], plan: dict, utc_offset: int = 0) -> dict:
    """Return a copy of plan whose intents cover the week with the given windows.

    Window times are local times for a zone `utc_offset` minutes ahead of UTC.
    Time not covered by a window is 'balance'. Overlapping windows raise MoixaError.
    """
    period = plan.get('periodDays', DEFAULT_PERIOD_DAYS) * MINUTES_PER_DAY
    pieces: list[tuple[int, int, dict]] = []
    for window in windows:
        start = window.start.hour * 60 + window.start.minute
        end = (window.end.hour * 60 + window.end.minute) or MINUTES_PER_DAY
        length = (end - start) % MINUTES_PER_DAY or MINUTES_PER_DAY
        intent = window.intent()
        for day in window.days:
            first = (day * MINUTES_PER_DAY + start - utc_offset) % period
            pieces.extend((a, b, intent) for a, b in _split_at_week_end(first, length, period))
    pieces.sort(key=lambda piece: piece[0])

    default_intent = build_intent('balance', DEFAULT_SOC_MIN, DEFAULT_SOC_MAX)
    covered: list[tuple[int, int, dict]] = []
    position = 0
    for start, end, intent in pieces:
        if start < position:
            raise MoixaError('Schedule windows overlap')
        if start > position:
            covered.append((position, start, default_intent))
        covered.append((start, end, intent))
        position = end
    if position < period:
        covered.append((position, period, default_intent))

    intents: list[dict] = []
    for _, end, intent in covered:
        if intents and intents[-1]['intent'] == intent:
            intents[-1]['durationMinutes'] = end
        else:
            intents.append({'intent': intent, 'durationMinutes': end})
    return {**plan, 'intents': intents}


def plan_to_windows(plan: dict, utc_offset: int = 0) -> list[ScheduleWindow]:
    """Return the plan as single-day windows in local time for a zone `utc_offset` minutes ahead of UTC.

    Windows are split at midnight and sorted by weekday and start time.
    """
    period = plan.get('periodDays', DEFAULT_PERIOD_DAYS) * MINUTES_PER_DAY
    slots = [(slot['durationMinutes'], slot['intent']) for slot in plan['intents']]
    if slots[-1][0] < period:
        slots.append((period, build_intent('balance', DEFAULT_SOC_MIN, DEFAULT_SOC_MAX)))
    windows: list[ScheduleWindow] = []
    start = 0
    for end, intent in slots:
        position = start
        while position < end:
            local = (position + utc_offset) % period
            day, minute = divmod(local, MINUTES_PER_DAY)
            step = min(end - position, MINUTES_PER_DAY - minute)
            windows.append(ScheduleWindow.from_intent(
                _time_of_day(minute), _time_of_day(minute + step), day, intent))
            position += step
        start = end
    return sorted(windows, key=lambda window: (window.days[0], window.start))


def _split_at_week_end(start: int, length: int, period: int) -> list[tuple[int, int]]:
    if start + length <= period:
        return [(start, start + length)]
    return [(start, period), (0, start + length - period)]


def _time_of_day(minute: int) -> time:
    return time(minute // 60 % 24, minute % 60)
