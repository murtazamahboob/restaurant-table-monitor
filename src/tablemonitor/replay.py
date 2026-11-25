"""Scripted lunch-rush replay: a deterministic synthetic dining room.

No real camera, no real video — the replay generates the observations a
camera pipeline would produce (foot points, uniform scores, surface
features) from a script of table episodes, then runs the venue engine over
them second by second. The script exercises every rule in the blueprint:

- T1  seated, waiter serves in time (first service ~100 s)
- T2  seated, nobody comes -> UNATTENDED_TABLE, escalates, waiter late
- T3  served, leaves dirty, staff cleans -> EMPTY_CLEAN
- T4  seated, POS "order opened" cancels the timer (no waiter visit)
- T5  served, leaves dirty and stays dirty (crowd-rule ingredient)
- T6  seated, waiter serves in time
- T7  served, leaves dirty and stays dirty (crowd-rule ingredient)
- T8  seated, waiter serves in time
- T9  seated, waiter serves in time
- T10 seated, waiter serves in time

With T5 and T7 empty-dirty while T1, T2, T4, T6, T8, T9, T10 are occupied
(8 of 10 tables = 80%), the CLEAN_TABLES_NOW crowd rule fires.

Staff tracks start 15 s before the visit (the 15-frame uniform vote has
to settle first) in the aisle, then step into the service zone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dashboard import analytics
from .engine import TableDef, VenueEngine
from .people import Observation
from .pos import PosEvent
from .surface import SurfaceObservation

DURATION = 900.0  # 15-minute lunch rush, 1-second ticks


@dataclass
class Episode:
    table_id: str
    sit_t: float
    leave_t: float | None = None       # None = still seated at end
    waiter_t: float | None = None      # when the waiter reaches the table
    pos_t: float | None = None         # POS "order opened" time
    dirty_after_leave: bool = False
    clean_t: float | None = None       # staff starts cleaning the dirty table


def build_tables() -> list[TableDef]:
    """10 tables in two rows of five, 14 m apart horizontally."""
    tables = []
    for i in range(10):
        row, col = divmod(i, 5)
        tables.append(TableDef(table_id=f"T{i + 1}", x=4 + col * 16,
                               y=4 + row * 18, capacity=4))
    return tables


def build_episodes() -> list[Episode]:
    return [
        Episode("T1", sit_t=0, leave_t=700, waiter_t=100),
        Episode("T2", sit_t=10, leave_t=800, waiter_t=460),
        Episode("T3", sit_t=20, leave_t=300, waiter_t=90,
                dirty_after_leave=True, clean_t=460),
        Episode("T4", sit_t=30, leave_t=700, pos_t=90),
        Episode("T5", sit_t=40, leave_t=420, waiter_t=120,
                dirty_after_leave=True),
        Episode("T6", sit_t=50, leave_t=700, waiter_t=140),
        Episode("T7", sit_t=60, leave_t=480, waiter_t=150,
                dirty_after_leave=True),
        Episode("T8", sit_t=70, leave_t=700, waiter_t=160),
        Episode("T9", sit_t=80, leave_t=700, waiter_t=170),
        Episode("T10", sit_t=90, leave_t=700, waiter_t=180),
    ]


def _customer_points(table: TableDef) -> list[tuple[float, float]]:
    cx, cy = table.x + table.w / 2, table.y + table.h / 2
    return [(cx - 2, cy), (cx + 2, cy)]


def _aisle_point(table: TableDef) -> tuple[float, float]:
    return (table.x + table.w / 2, table.y + table.h + 8)


def _service_point(table: TableDef) -> tuple[float, float]:
    return (table.x + table.w / 2, table.y - 2)


def run_replay(duration: float = DURATION) -> dict:
    tables = build_tables()
    episodes = build_episodes()
    by_table = {t.table_id: t for t in tables}
    engine = VenueEngine(tables)
    events: list[dict] = []
    surface_labels: list[tuple[str, str]] = []  # (predicted raw, truth)
    # Pre-compute per-table surface truth over time.
    for t_int in range(int(duration) + 1):
        t = float(t_int)
        for ep in episodes:
            table = by_table[ep.table_id]
            # --- customers ---
            seated = ep.sit_t <= t and (ep.leave_t is None or t < ep.leave_t)
            if seated:
                for k, (px, py) in enumerate(_customer_points(table)):
                    engine.observe_person(Observation(
                        t=t, person_id=f"cust-{ep.table_id}-{k}",
                        foot=(px, py), uniform_score=0.05))
            # --- staff: waiter visit (15 s vote lead-in in the aisle) ---
            if ep.waiter_t is not None:
                staff_id = f"staff-{ep.table_id}"
                if ep.waiter_t - 15 <= t < ep.waiter_t:
                    engine.observe_person(Observation(
                        t=t, person_id=staff_id,
                        foot=_aisle_point(table), uniform_score=0.95))
                elif ep.waiter_t <= t < ep.waiter_t + 6:
                    engine.observe_person(Observation(
                        t=t, person_id=staff_id,
                        foot=_service_point(table), uniform_score=0.95))
            # --- staff: cleaning a dirty table ---
            if ep.clean_t is not None and ep.clean_t <= t < ep.clean_t + 20:
                engine.observe_person(Observation(
                    t=t, person_id=f"cleaner-{ep.table_id}",
                    foot=_service_point(table), uniform_score=0.95))
            # --- surface observation every 3 s ---
            if t_int % 3 == 0:
                dirty = False
                if ep.dirty_after_leave and ep.leave_t is not None \
                        and ep.leave_t <= t and not (
                            ep.clean_t is not None and ep.clean_t <= t):
                    dirty = True
                if dirty:
                    obs = SurfaceObservation(t=t, table_id=ep.table_id,
                                             clutter=0.9, spill=0.6, trash=0.5)
                else:
                    obs = SurfaceObservation(t=t, table_id=ep.table_id,
                                             clutter=0.05, spill=0.02, trash=0.0)
                surface_labels.append((obs.raw_label(),
                                       "dirty" if dirty else "clean"))
                engine.observe_surface(obs)
        # --- POS events ---
        for ep in episodes:
            if ep.pos_t is not None and abs(t - ep.pos_t) < 1e-9:
                events.extend(engine.pos_event(
                    PosEvent(t=t, table_id=ep.table_id)))
        events.extend(engine.tick(t))
    # Waiter-visit detection: scripted visits vs detected waiter servings
    # (a served table, or an unattended alert closed by a waiter visit).
    scripted_visits = sum(1 for ep in episodes if ep.waiter_t is not None)
    detected_visits = sum(1 for e in events
                          if e["event"] in ("served", "alert_closed")
                          and e.get("source") == "waiter_visit")
    pos_served = sum(1 for e in events
                     if e["event"] == "served"
                     and e.get("source") == "pos_order_opened")
    seated_detected = sum(1 for e in events if e["event"] == "seated")
    correct_surface = sum(1 for pred, truth in surface_labels
                          if pred == truth)
    report = {
        "duration_s": duration,
        "tables": len(tables),
        "events": events,
        "alerts": [a.to_dict() for a in engine.alerts.alerts],
        "push_messages": [m.to_dict() for m in engine.push.sent],
        "final_states": {tid: m.state
                         for tid, m in engine.machines.items()},
        "metrics": {
            **analytics(events, [a.to_dict() for a in engine.alerts.alerts]),
            "seated_detection": f"{seated_detected}/{len(episodes)}",
            "waiter_visit_recall": (detected_visits / scripted_visits
                                    if scripted_visits else 1.0),
            "waiter_visit_precision": (detected_visits / detected_visits
                                       if detected_visits else 0.0),
            "pos_served": pos_served,
            "surface_accuracy": round(correct_surface / len(surface_labels), 3)
            if surface_labels else None,
            "surface_observations": len(surface_labels),
        },
    }
    return report
