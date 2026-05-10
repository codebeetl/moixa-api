from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .auth import MoixaCognitoAuth, TokenStore
from .client import MoixaClient
from .exceptions import MoixaAuthError, MoixaError
from . import parse_jts

mcp = FastMCP("Moixa GridShare")

_client: Optional[MoixaClient] = None
_site_id: Optional[str] = None
_battery_id: Optional[str] = None


def _get_client() -> MoixaClient:
    global _client
    if _client is not None:
        return _client
    try:
        tokens = TokenStore().load()
    except MoixaAuthError:
        username = os.environ.get('MOIXA_USERNAME')
        password = os.environ.get('MOIXA_PASSWORD')
        if not username or not password:
            raise MoixaAuthError(
                'No saved tokens at ~/.moixa_tokens.json. '
                'Set MOIXA_USERNAME and MOIXA_PASSWORD env vars, or run test.py first.'
            )
        tokens = MoixaCognitoAuth(username, password).login()
        TokenStore().save(tokens)
    _client = MoixaClient(tokens)
    return _client


def _get_site_id() -> str:
    global _site_id, _battery_id
    if _site_id is None:
        site_users = _get_client().get_site_users()
        _site_id = site_users[0]['siteId']
        for device in site_users[0]['devices']:
            if device['deviceType'] == 'VirtualMoixaVictronSmartBattery':
                _battery_id = device['id']
                break
    return _site_id


def _get_battery_id() -> str:
    _get_site_id()
    if not _battery_id:
        raise MoixaError('No battery device found for this account')
    return _battery_id


def _iso(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_battery_level() -> float:
    """Current battery state of charge as a fraction from 0.0 (empty) to 1.0 (full)."""
    return _get_client().get_current_battery_level()


@mcp.tool()
def get_site_info() -> dict:
    """Site ID, vendor, and list of connected devices (hub, battery, meter) for this account."""
    return _get_client().get_site_users()[0]


@mcp.tool()
def get_user_info() -> dict:
    """Account metadata: email, vendor, status, and account creation date."""
    return _get_client().get_user_metadata()


@mcp.tool()
def get_power_readings() -> list:
    """Latest real-time power flow: consumption, grid import/export, solar generation, battery in/out (all in watts)."""
    return parse_jts(_get_client().get_core_readings(_get_site_id()))


@mcp.tool()
def get_device_readings() -> list:
    """Latest per-device readings for the battery: consumption, grid, production, storage power (W) and state of charge."""
    return parse_jts(_get_client().get_device_status(_get_battery_id()))


@mcp.tool()
def get_forecasts(hours_ahead: int = 24) -> list:
    """Predicted consumption and solar production for the next N hours at 30-minute resolution.

    Args:
        hours_ahead: Number of hours to forecast. Default 24.
    """
    now = datetime.now(timezone.utc)
    return parse_jts(_get_client().get_site_forecasts(
        _get_site_id(), _iso(now), _iso(now + timedelta(hours=hours_ahead))
    ))


@mcp.tool()
def get_tariffs(hours_ahead: int = 24) -> list:
    """Electricity tariff prices for the next N hours (e.g. Octopus Agile half-hourly rates).

    Args:
        hours_ahead: Number of hours of tariff data. Default 24.
    """
    now = datetime.now(timezone.utc)
    return _get_client().get_device_tariff_time_series(
        _get_battery_id(), _iso(now), _iso(now + timedelta(hours=hours_ahead))
    )


@mcp.tool()
def get_operation_mode() -> dict:
    """Current battery operation mode ('smart', 'schedule', or 'simple') and the active plan."""
    return _get_client().get_device_current_operation_mode(_get_battery_id())


@mcp.tool()
def get_schedule() -> list:
    """Weekly charge/discharge schedule as a list of intent slots with kind, duration, and SOC limits."""
    schedule = _get_client().get_device_operation_schedule(_get_battery_id())
    return schedule['plan']['intents']


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

@mcp.tool()
def set_operation_mode(mode: str) -> str:
    """Switch the battery operation mode.

    Args:
        mode: One of 'smart' (Moixa-managed), 'schedule' (follows weekly plan), or 'simple'.
    """
    if mode not in ('smart', 'schedule', 'simple'):
        raise MoixaError(f"Invalid mode {mode!r}. Choose from: smart, schedule, simple.")
    _get_client().set_device_operation_mode(_get_battery_id(), mode)
    return f"Operation mode set to '{mode}'."


@mcp.tool()
def add_schedule_slot(
    kind: str,
    duration_minutes: int,
    position: int = -1,
    soc_min: float = 0.1,
    soc_max: float = 1.0,
    power_watts: Optional[float] = None,
) -> str:
    """Insert a new slot into the weekly charge/discharge schedule.

    Args:
        kind: 'balance' (smart balancing), 'charge/discharge' (forced), or 'idle' (do nothing).
        duration_minutes: Length of the slot in minutes.
        position: Where to insert the slot (0 = start, -1 = end). Default -1.
        soc_min: Minimum allowed battery SOC, 0.0-1.0. Default 0.1.
        soc_max: Maximum allowed battery SOC, 0.0-1.0. Default 1.0.
        power_watts: Charge/discharge power in watts. Required for 'charge/discharge' kind.
    """
    _get_client().add_schedule_intent(
        _get_battery_id(),
        kind=kind,
        duration_minutes=duration_minutes,
        position=position,
        soc_min=soc_min,
        soc_max=soc_max,
        power_watts=power_watts,
    )
    return f"Added {kind} slot of {duration_minutes} min at position {position}."


@mcp.tool()
def edit_schedule_slot(
    index: int,
    kind: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    soc_min: Optional[float] = None,
    soc_max: Optional[float] = None,
    power_watts: Optional[float] = None,
) -> str:
    """Edit an existing schedule slot. Only the fields you supply are changed.

    Args:
        index: Slot index (from get_schedule).
        kind: New kind: 'balance', 'charge/discharge', or 'idle'.
        duration_minutes: New duration. The difference is absorbed by the neighbouring slot.
        soc_min: New minimum SOC limit, 0.0-1.0.
        soc_max: New maximum SOC limit, 0.0-1.0.
        power_watts: New charge/discharge power in watts.
    """
    _get_client().edit_schedule_intent(
        _get_battery_id(),
        index=index,
        kind=kind,
        duration_minutes=duration_minutes,
        soc_min=soc_min,
        soc_max=soc_max,
        power_watts=power_watts,
    )
    return f"Updated schedule slot {index}."


@mcp.tool()
def delete_schedule_slot(index: int) -> str:
    """Delete a schedule slot by index. Its duration is returned to the neighbouring slot.

    Args:
        index: Slot index to delete (from get_schedule).
    """
    _get_client().delete_schedule_intent(_get_battery_id(), index)
    return f"Deleted schedule slot {index}."


def main() -> None:
    mcp.run()
