# Restaurant Table Monitor — Every Table Watched, No Waiter Left Waiting

**Camera-based table state, service timers and alerts for restaurants and cafes — fully offline, deterministic, pure NumPy.** Restaurants lose money when a seated customer waits too long for a waiter and when dirty tables block seating during rush. This system watches the dining room, understands each table (clean, dirty, occupied, waiting), runs a 5-minute service timer per table, and alerts the live dashboard — with waiter-phone push, POS integration, and privacy built in: faces are blurred and no video is ever stored.

## Results (measured, not claimed)

Replay: a scripted 15-minute lunch rush over 10 tables, run twice — including in a fresh venv installed from `requirements.txt` only — with identical outputs. Run it yourself with `tablemonitor demo`.

| Metric | Measured |
|---|---|
| Test suite | **36/36 tests pass**, verified twice — including in a fresh venv |
| Seated detection | **10/10** tables detected occupied |
| Waiter-visit recall / precision | **1.000 / 1.000** (9 scripted visits, all detected, no false positives) |
| Surface classifier accuracy | **1.000** over 3,010 labelled observations |
| POS-cancelled timers | **1** (T4 served by a POS "order opened" event, no waiter visit) |
| First service | mean **122.8 s**, 9/10 under 300 s; the one miss (T2, 452 s) raised an alert |
| Unattended alerts | **1** (T2, escalated to critical after +2 min, closed by the late waiter) |
| Clean-tables-now alerts | **1** (8/10 tables occupied with T3 + T5 empty and dirty) |
| Tables cleaned | **1** (T3, staff-cleaned back to EMPTY_CLEAN) |
| Runtime dependencies | **NumPy only** — no YOLO, no GPU, no network, no API key |

The honest finding is in the table, not hidden from it: the system catches the failure it is built for — T2 waits 452 s and is escalated — instead of reporting only the nine tables that were served on time.

## Features

- **Per-table state machine** — `EMPTY_CLEAN → OCCUPIED_WAITING → OCCUPIED_SERVED → EMPTY_DIRTY → EMPTY_CLEAN`, plus `ALERT_UNATTENDED`, exactly as specified in the blueprint: seating confirmed after 25 s in the zone (timer starts at first seat, not at confirmation), waiter visit is 3 s in the service zone, leaving needs 45 s with nobody in the zone, cleaning needs a clean surface for 10 s *and* staff present.
- **5-minute service timer, per table** — configurable per table or time of day (default 300 s). On expiry it raises `UNATTENDED_TABLE` with table number, seat time and wait length, and escalates to critical after a further 2 minutes.
- **Clean-or-dirty surface classifier with 10 s smoothing** — clutter / spill / trash scored by a fixed-weight rule; the reported state only flips after the same answer holds for 10 s, so a passing hand never flips a table.
- **Staff vs customer, voted over 15 frames** — uniform-colour score voted across 15 frames before anyone counts as staff, so a customer in a similar shirt does not cancel a timer.
- **Crowd rule** — occupancy ≥ 80% *and* ≥ 2 (or ≥ 20%) tables empty and dirty raises `CLEAN_TABLES_NOW`, repeated every 5 minutes until resolved.
- **POS integration** — a POS event `"order opened for table N"` cancels the timer exactly like a waiter visit (the blueprint's most accurate cancel signal). Events arrive as plain JSON dicts; no vendor SDK.
- **Waiter-phone push alerts** — every alert is fanned out to a waiter-phone outbox and a manager Telegram channel as JSON messages; the outbox is the boundary a real sender reads from.
- **Privacy-first** — faces are box-blurred before any frame is analysed, and frames are never written to disk: only events (table, state, timestamps) are logged. `FrameStore` is an explicit no-op so the guarantee is greppable.
- **Camera health + drift checks** — low frame rate, frozen frames, and surface-score drift away from the calibrated baseline are reported as `DEGRADED` with the cause named.
- **Live floor-map dashboard** — `tablemonitor demo` writes `outputs/floor-map.html`: an SVG floor map coloured by table state, with the alert panel beside it. No server needed.
- **Analytics** — first-service mean/max, seatings, unattended count, tables cleaned, all from the replay's event log.

## How it works

```
camera (5-10 fps) → foot-point tracks → zone assignment → state machine + timers
                  → surface classifier (10 s smoothing) → alert engine → dashboard + push
```

A table has a seating polygon and a larger service polygon. A person belongs to a table when their foot point (bottom centre of the box) is inside the zone. In this repo the camera pipeline is replaced by a deterministic synthetic replay — same observations, same engine — so everything runs offline with no video. A real deployment swaps the observation source for RTSP + detector + tracker without changing the state machine, alerts or dashboard.

## Quickstart

```bash
pip install -r requirements.txt
pip install -e .

# Bundled demo: replay the scripted 15-minute lunch rush
tablemonitor demo

# Print the event timeline instead
tablemonitor replay

# Or run the demo script directly
python examples/demo.py
```

## Python API

```python
from tablemonitor import VenueEngine, build_tables, run_replay

report = run_replay()          # 900 s scripted lunch rush, 10 tables
print(report["metrics"])       # seated 10/10, waiter recall 1.000, ...

# Or drive the engine yourself, one tick per second:
engine = VenueEngine(build_tables())
engine.observe_person(...)     # Observation(t, person_id, foot, uniform_score)
engine.observe_surface(...)    # SurfaceObservation(t, table_id, clutter, spill, trash)
engine.pos_event(PosEvent(t=90, table_id="T4"))
engine.tick(90.0)
```

## Project structure

```
src/tablemonitor/
  geometry.py       point-in-polygon, foot points, table zones
  people.py         tracks, 15-frame staff vote, zone assignment
  surface.py        clean/dirty classifier with 10 s smoothing
  state_machine.py  one state machine per table (blueprint §6.4)
  alerts.py         UNATTENDED_TABLE, escalation, CLEAN_TABLES_NOW
  pos.py            POS events + waiter-phone / Telegram push outbox
  privacy.py        face blur, no-video-stored guarantee
  health.py         camera FPS / frozen / drift checks
  dashboard.py      SVG floor-map HTML + analytics
  engine.py         venue engine: one tick per second over all tables
  replay.py         scripted 15-minute lunch rush (10 tables)
  cli.py            `tablemonitor demo | replay | dashboard`
examples/demo.py    runs the replay, writes outputs/
tests/              36 tests: state machine, rules, perception, privacy, replay
```

## Limitations (stated plainly)

- The bundled replay is synthetic: people are foot points and surface features are numbers, not pixels. Seated-detection and waiter-visit numbers are measured against that script, not against real camera footage — a real pilot needs the two-week shadow-mode replay against recorded video the blueprint asks for.
- The staff classifier uses uniform colour only; a venue whose staff do not wear a uniform needs the small trained classifier the blueprint describes.
- The dashboard is a static HTML snapshot regenerated per replay, not a live WebSocket feed; the alert engine and push outbox are the seams a live server would attach to.
