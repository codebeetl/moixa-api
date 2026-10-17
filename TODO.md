# TODO

## Schedule helpers corrupt the weekly schedule

- [ ] Confirm what `durationMinutes` means in the schedule plan. On a live battery the slots of a 15-slot week read 629, 898, 2069, 2338 ... 10019 (ascending, repeating daily, none above 10080), so they look like end offsets within the 7-day period. A single all-week slot made in the GridShare web UI reads 10019. `add_schedule_intent`, `edit_schedule_intent` and `delete_schedule_intent` treat the values as slot lengths. Check against the API with the battery in `smart` mode, so the schedule is inactive.
- [ ] Fix the three helpers so every edit leaves a valid schedule. Deleting the last slot of the live schedule produced 19378, which is more than 10080.
- [ ] Validate a schedule before the PUT: values in range, ordered, no empty slot, kinds known, `power_watts` set for `charge/discharge`, `soc_min <= soc_max`.
- [ ] Replace the helper tests in `tests/test_client.py` (they build schedules from slot lengths) once the format is confirmed.
- [ ] Apply the same fix to the MCP tools `add_schedule_slot`, `edit_schedule_slot` and `delete_schedule_slot` in `moixa_py/mcp_server.py`.

## Easy schedule changes

- [ ] Add a pure schedule module that reads a plan into readable windows (weekday, start, end, kind, power, SoC limits) and builds a plan from such windows. Gaps become `balance`.
- [ ] Add `set_schedule(device_id, windows)` to the client. It writes the whole week in one PUT.
- [ ] Support all-week and per-weekday windows, such as "charge to 100% all day, every day".
- [ ] Take window times in local time. The plan is aligned to Monday 00:00 UTC, so decide how clock changes are handled (UK clocks change on 25 Oct 2026).
- [ ] Add `get_schedule` output as readable windows next to the raw plan, and accept a raw plan back, so a schedule can be saved and restored.
- [ ] Add the same operations to the MCP server and the CLI.
- [ ] Update the README schedule section.

## Follow-up in the ha-moixa repo

`custom_components/moixa/moixa_py/` is overwritten nightly from this repo, so the client changes arrive there on their own. The remaining work is in `ha-moixa`:

- [ ] Add `moixa.set_schedule` and `moixa.get_schedule` services (`services.yaml`, `__init__.py`, `coordinator.py`, `translations`).
- [ ] Add readable windows to the `schedule` attribute of the Operation Mode select.
- [ ] Fix the README example "Free-energy charge window". It adds a slot to the end of the week, not at the stated time.
- [ ] Add tests in `tests/test_services.py`.
- [ ] Keep the Home Assistant automation `automation.moixa_charge_during_octoplus_free_electricity` working. It only changes the operation mode and needs a schedule with an all-week charge slot.
