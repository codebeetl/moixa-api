from __future__ import annotations

from .exceptions import MoixaError

MINUTES_PER_DAY = 1440
DEFAULT_PERIOD_DAYS = 7
INTENT_KINDS = ('balance', 'charge/discharge', 'idle')


def build_intent(kind: str, soc_min: float, soc_max: float,
                 power_watts: float | None = None,
                 power_watts_min: float | None = None,
                 power_watts_max: float | None = None) -> dict:
    """Build the intent dict for a slot."""
    if kind not in INTENT_KINDS:
        raise MoixaError(f"Unknown intent kind {kind!r}. Use 'balance', 'charge/discharge', or 'idle'.")
    intent: dict = {'kind': kind, 'socMin': soc_min, 'socMax': soc_max}
    if kind == 'charge/discharge':
        if power_watts is None:
            raise MoixaError("power_watts is required for 'charge/discharge' intent")
        intent['powerWatts'] = power_watts
    elif kind == 'balance':
        intent['powerWattsMin'] = power_watts_min if power_watts_min is not None else -20
        intent['powerWattsMax'] = power_watts_max if power_watts_max is not None else 20
    return intent


def slot_lengths(plan: dict) -> list[int]:
    """Return each slot's length in minutes. A slot's durationMinutes is its end offset within the period."""
    ends = [slot['durationMinutes'] for slot in plan['intents']]
    return [end - start for start, end in zip([0] + ends, ends)]


def set_slot_lengths(plan: dict, lengths: list[int]) -> None:
    """Write slot lengths back as end offsets. The plan must hold one slot per length."""
    end = 0
    for slot, length in zip(plan['intents'], lengths):
        end += length
        slot['durationMinutes'] = end


def validate_plan(plan: dict) -> None:
    """Raise MoixaError unless the plan is a valid weekly schedule."""
    intents = plan.get('intents')
    if not intents:
        raise MoixaError('Schedule has no slots')
    period_minutes = plan.get('periodDays', DEFAULT_PERIOD_DAYS) * MINUTES_PER_DAY
    previous_end = 0
    for index, slot in enumerate(intents):
        end = slot['durationMinutes']
        if end <= previous_end:
            raise MoixaError(f'Slot {index} ends at {end}, which is not after the previous end {previous_end}')
        if end > period_minutes:
            raise MoixaError(f'Slot {index} ends at {end}, past the end of the period ({period_minutes})')
        previous_end = end
        _validate_intent(index, slot['intent'])


def _validate_intent(index: int, intent: dict) -> None:
    kind = intent.get('kind')
    if kind not in INTENT_KINDS:
        raise MoixaError(f'Slot {index} has unknown kind {kind!r}')
    if kind == 'charge/discharge' and intent.get('powerWatts') is None:
        raise MoixaError(f'Slot {index} is charge/discharge but has no powerWatts')
    if intent['socMin'] > intent['socMax']:
        raise MoixaError(f'Slot {index} has socMin above socMax')
