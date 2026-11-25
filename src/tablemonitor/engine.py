"""Venue engine: one tick per second over all tables.

Per tick: consume person + surface observations, run each table's state
machine, open/close/escalate alerts, apply the crowd rule, and fan alerts
out to the waiter-phone outbox. POS events cancel a waiting timer the
same way a waiter visit does.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .alerts import AlertEngine
from .geometry import Polygon, expand_polygon, rect_polygon
from .people import Observation, Tracker
from .pos import PosEvent, PushOutbox
from .state_machine import TableConfig, TableStateMachine
from .surface import SurfaceClassifier, SurfaceObservation


@dataclass
class TableDef:
    table_id: str
    x: float
    y: float
    w: float = 8.0
    h: float = 6.0
    capacity: int = 4
    service_timer: float = 300.0

    @property
    def seating(self) -> Polygon:
        return rect_polygon(self.x, self.y, self.w, self.h)

    @property
    def service(self) -> Polygon:
        return expand_polygon(self.seating, 4.0)


@dataclass
class VenueEngine:
    tables: list[TableDef]
    machines: dict[str, TableStateMachine] = field(default_factory=dict)
    surfaces: dict[str, SurfaceClassifier] = field(default_factory=dict)
    tracker: Tracker = field(default_factory=Tracker)
    alerts: AlertEngine = field(default_factory=AlertEngine)
    push: PushOutbox = field(default_factory=PushOutbox)
    now: float = 0.0

    def __post_init__(self) -> None:
        for td in self.tables:
            self.machines[td.table_id] = TableStateMachine(
                TableConfig(table_id=td.table_id, capacity=td.capacity,
                            service_timer=td.service_timer))
            self.surfaces[td.table_id] = SurfaceClassifier(td.table_id)

    def table_def(self, table_id: str) -> TableDef:
        return next(t for t in self.tables if t.table_id == table_id)

    def observe_person(self, obs: Observation) -> None:
        self.tracker.observe(obs)

    def observe_surface(self, obs: SurfaceObservation) -> None:
        self.surfaces[obs.table_id].observe(obs)

    def pos_event(self, event: PosEvent) -> list[dict]:
        machine = self.machines[event.table_id]
        if event.kind == "order_opened":
            raised = machine.pos_order_opened(event.t)
            for ev in raised:
                self._handle_machine_events(event.t, ev)
            return raised
        return []

    def tick(self, t: float, dt: float = 1.0) -> list[dict]:
        self.now = t
        # Drop tracks with no detection for a while, so a table that
        # customers have left stops counting them as seated.
        self.tracker.prune(t)
        raised: list[dict] = []
        for td in self.tables:
            machine = self.machines[td.table_id]
            customers = self.tracker.in_zone(td.seating, t, role="customer")
            staff = self.tracker.in_zone(td.service, t, role="staff")
            surface = self.surfaces[td.table_id].state
            for ev in machine.tick(t, len(customers), len(staff), surface, dt):
                raised.append(ev)
                self._handle_machine_events(t, ev)
        for alert in self.alerts.escalate(t):
            self.push.send_alert(alert.alert_id, alert.kind, alert.table_id,
                                 t, alert.severity)
        dirty_empty = [tid for tid, m in self.machines.items()
                       if m.state == "EMPTY_DIRTY"]
        n_occupied = sum(1 for m in self.machines.values() if m.is_occupied)
        crowd = self.alerts.check_crowd_rule(t, len(self.tables), n_occupied,
                                             dirty_empty)
        if crowd is not None:
            self.push.send_alert(crowd.alert_id, crowd.kind, None, t,
                                 crowd.severity)
            raised.append({"t": t, "event": "clean_tables_now",
                           "tables": crowd.detail["tables"]})
        return raised

    def _handle_machine_events(self, t: float, ev: dict) -> None:
        if ev["event"] == "unattended_alert":
            alert = self.alerts.open_unattended(ev["table"], t,
                                                ev.get("waited", 0.0))
            if alert is not None:
                self.push.send_alert(alert.alert_id, alert.kind,
                                     alert.table_id, t, alert.severity)
        elif ev["event"] == "alert_closed":
            self.alerts.close_unattended(ev["table"], t)

    def snapshot(self) -> list[dict]:
        out = []
        for td in self.tables:
            machine = self.machines[td.table_id]
            out.append({"id": td.table_id, "x": td.x, "y": td.y,
                        "w": td.w, "h": td.h, "state": machine.state,
                        "capacity": td.capacity,
                        "waiting_s": machine.waiting_at(self.now)
                        if machine.is_occupied else None})
        return out
