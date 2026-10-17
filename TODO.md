# TODO

## Schedule helpers corrupt the weekly schedule

- [x] Confirm what `durationMinutes` means in the schedule plan. Decided: it is the end offset within the 7-day period. Not yet checked against the API with the battery in `smart` mode.
- [x] Fix the three helpers so every edit leaves a valid schedule.
- [x] Validate a schedule before the PUT: values in range, ordered, no empty slot, kinds known, `power_watts` set for `charge/discharge`, `soc_min <= soc_max`.
- [x] Replace the helper tests in `tests/test_client.py`.
- [x] Apply the same fix to the MCP tools `add_schedule_slot`, `edit_schedule_slot` and `delete_schedule_slot` in `moixa_py/mcp_server.py`.

## Easy schedule changes

- [x] Add a pure schedule module that reads a plan into readable windows (weekday, start, end, kind, power, SoC limits) and builds a plan from such windows. Gaps become `balance`.
- [x] Add `set_schedule(device_id, windows)` to the client. It writes the whole week in one PUT.
- [x] Support all-week and per-weekday windows, such as "charge to 100% all day, every day".
- [x] Take window times in local time. Decided: an IANA `tz` argument, default UTC. Its offset at one moment is applied to the whole week, so `set_schedule` must run again after a clock change.
- [x] Add `get_schedule` output as readable windows next to the raw plan, and accept a raw plan back, so a schedule can be saved and restored. A raw plan is restored with `set_device_operation_schedule`.
- [ ] Add the same operations to the MCP server and the CLI.
- [x] Update the README schedule section.

## Follow-up in the ha-moixa repo

`custom_components/moixa/moixa_py/` is overwritten nightly from this repo, so the client changes arrive there on their own. The remaining work is in `ha-moixa`:

- [ ] Add `moixa.set_schedule` and `moixa.get_schedule` services (`services.yaml`, `__init__.py`, `coordinator.py`, `translations`).
- [ ] Add readable windows to the `schedule` attribute of the Operation Mode select.
- [ ] Fix the README example "Free-energy charge window". It adds a slot to the end of the week, not at the stated time.
- [ ] Add tests in `tests/test_services.py`.
- [ ] Keep the Home Assistant automation `automation.moixa_charge_during_octoplus_free_electricity` working. It only changes the operation mode and needs a schedule with an all-week charge slot.
