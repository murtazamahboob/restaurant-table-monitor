"""Alert engine: UNATTENDED_TABLE with escalation, and the venue-level
CLEAN_TABLES_NOW crowd rule. Alerts are stored, deduplicated by cooldown,
pushed to the waiter-phone outbox, and closed when the underlying condition
clears.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ESCALATE_AFTER_SECONDS = 120.0
CLEAN_NOW_REPEAT_SECONDS = 300.0
CROWD_OCCUPANCY = 0.80
CROWD_DIRTY_COUNT = 2
CROWD_DIRTY_FRACTION = 0.20


@dataclass
class Alert:
    alert_id: str
    kind: str  # UNATTENDED_TABLE | CLEAN_TABLES_NOW
    table_id: str | None
    created_t: float
    severity: str = "warning"  # warning -> critical on escalation
    status: str = "open"
    detail: dict = field(default_factory=dict)
    closed_t: float | None = None

    def to_dict(self) -> dict:
        return {"id": self.alert_id, "kind": self.kind,
                "table": self.table_id, "created_t": self.created_t,
                "severity": self.severity, "status": self.status,
                "detail": self.detail, "closed_t": self.closed_t}


class AlertEngine:
    def __init__(self) -> None:
        self.alerts: list[Alert] = []
        self._seq = 0
        self._last_clean_now_t: float | None = None

    def _new(self, kind: str, table_id: str | None, t: float,
             **detail) -> Alert:
        self._seq += 1
        alert = Alert(alert_id=f"A{self._seq:04d}", kind=kind,
                      table_id=table_id, created_t=t, detail=detail)
        self.alerts.append(alert)
        return alert

    def open_unattended(self, table_id: str, t: float,
                        waited: float) -> Alert | None:
        if any(a.kind == "UNATTENDED_TABLE" and a.table_id == table_id
               and a.status == "open" for a in self.alerts):
            return None
        return self._new("UNATTENDED_TABLE", table_id, t, waited=waited)

    def close_unattended(self, table_id: str, t: float) -> Alert | None:
        for alert in self.alerts:
            if (alert.kind == "UNATTENDED_TABLE"
                    and alert.table_id == table_id and alert.status == "open"):
                alert.status = "closed"
                alert.closed_t = t
                return alert
        return None

    def escalate(self, now: float) -> list[Alert]:
        """UNATTENDED_TABLE open for a further 2 minutes -> critical."""
        out = []
        for alert in self.alerts:
            if (alert.kind == "UNATTENDED_TABLE" and alert.status == "open"
                    and alert.severity == "warning"
                    and now - alert.created_t >= ESCALATE_AFTER_SECONDS):
                alert.severity = "critical"
                out.append(alert)
        return out

    def check_crowd_rule(self, t: float, n_tables: int, n_occupied: int,
                         dirty_empty_tables: list[str]) -> Alert | None:
        """Occupancy >= 80% and >= 2 (or >= 20%) tables empty+dirty ->
        CLEAN_TABLES_NOW, repeated every 5 minutes until resolved."""
        if n_tables == 0:
            return None
        if n_occupied / n_tables < CROWD_OCCUPANCY:
            return None
        if not (len(dirty_empty_tables) >= CROWD_DIRTY_COUNT
                or len(dirty_empty_tables) / n_tables >= CROWD_DIRTY_FRACTION):
            return None
        if self._last_clean_now_t is not None \
                and t - self._last_clean_now_t < CLEAN_NOW_REPEAT_SECONDS:
            return None
        self._last_clean_now_t = t
        return self._new("CLEAN_TABLES_NOW", None, t,
                         tables=sorted(dirty_empty_tables),
                         occupancy=n_occupied / n_tables)

    @property
    def open_alerts(self) -> list[Alert]:
        return [a for a in self.alerts if a.status == "open"]
