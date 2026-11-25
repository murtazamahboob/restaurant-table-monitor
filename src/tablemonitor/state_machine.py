"""One state machine per table, exactly as the blueprint's section 6.4.

States
------
EMPTY_CLEAN      no customers, surface clean
OCCUPIED_WAITING customers seated, 5-minute timer running from first seat
ALERT_UNATTENDED timer expired with no staff visit
OCCUPIED_SERVED  staff visited (or POS order opened), timer cancelled
LEAVING          customers gone, 45 s grace before the table is "left"
EMPTY_DIRTY      customers gone, surface dirty, needs cleaning
ALERT_CLEAN_NOW  venue-level crowd rule (raised by the alert engine, not here)

Timers are in seconds and all thresholds are configurable per table.
The machine consumes one tick per second with the current zone counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SEAT_CONFIRM_SECONDS = 25.0   # 20-30 s in the blueprint
WAITER_VISIT_SECONDS = 3.0
LEAVE_GRACE_SECONDS = 45.0
CLEAN_CONFIRM_SECONDS = 10.0
SERVICE_TIMER_SECONDS = 300.0  # 5 minutes
ESCALATE_AFTER_SECONDS = 120.0  # +2 minutes -> critical


@dataclass
class TableConfig:
    table_id: str
    capacity: int = 4
    service_timer: float = SERVICE_TIMER_SECONDS
    seat_confirm: float = SEAT_CONFIRM_SECONDS
    waiter_visit: float = WAITER_VISIT_SECONDS
    leave_grace: float = LEAVE_GRACE_SECONDS


@dataclass
class TableStateMachine:
    config: TableConfig
    state: str = "EMPTY_CLEAN"
    seat_time: float | None = None        # first-seat time (timer origin)
    first_service_time: float | None = None
    served_at: float | None = None
    alert_raised_at: float | None = None
    # Internal accumulators (seconds of continuous condition).
    _seated_for: float = 0.0
    _staff_for: float = 0.0
    _empty_for: float = 0.0
    _clean_for: float = 0.0
    _staff_seen_cleaning: bool = False
    events: list[dict] = field(default_factory=list)

    def _log(self, t: float, event: str, **extra) -> None:
        self.events.append({"t": t, "table": self.config.table_id,
                            "event": event, "state": self.state, **extra})

    def tick(self, t: float, customers_in_zone: int, staff_in_service: int,
             surface: str, dt: float = 1.0) -> list[dict]:
        """Advance one tick. Returns the events raised on this tick."""
        before = len(self.events)
        cfg = self.config
        if customers_in_zone > 0:
            self._seated_for += dt
            self._empty_for = 0.0
        else:
            self._seated_for = 0.0
            self._empty_for += dt
        if staff_in_service > 0:
            self._staff_for += dt
        else:
            self._staff_for = 0.0
        if surface == "clean":
            self._clean_for += dt
            if staff_in_service > 0:
                self._staff_seen_cleaning = True
        else:
            self._clean_for = 0.0
            self._staff_seen_cleaning = False

        if self.state == "EMPTY_CLEAN":
            if customers_in_zone > 0 and self._seated_for >= cfg.seat_confirm:
                self.state = "OCCUPIED_WAITING"
                self.seat_time = t - self._seated_for + dt
                self._log(t, "seated", seat_time=self.seat_time)
        elif self.state == "OCCUPIED_WAITING":
            if self._staff_for >= cfg.waiter_visit:
                self._serve(t, source="waiter_visit")
            elif self.seat_time is not None and t - self.seat_time >= cfg.service_timer:
                self.state = "ALERT_UNATTENDED"
                self.alert_raised_at = t
                self._log(t, "unattended_alert", waited=t - self.seat_time)
        elif self.state == "ALERT_UNATTENDED":
            if self._staff_for >= cfg.waiter_visit:
                self._serve(t, source="waiter_visit")
        elif self.state == "OCCUPIED_SERVED":
            if customers_in_zone == 0 and self._empty_for >= cfg.leave_grace:
                if surface == "dirty":
                    self.state = "EMPTY_DIRTY"
                    self._log(t, "left_dirty")
                else:
                    self.state = "EMPTY_CLEAN"
                    self._log(t, "left_clean")
                self.seat_time = None
        elif self.state == "EMPTY_DIRTY":
            if (surface == "clean" and self._clean_for >= CLEAN_CONFIRM_SECONDS
                    and self._staff_seen_cleaning):
                self.state = "EMPTY_CLEAN"
                self._log(t, "cleaned")
        return self.events[before:]

    def _serve(self, t: float, source: str) -> None:
        self.state = "OCCUPIED_SERVED"
        self.served_at = t
        if self.seat_time is not None:
            self.first_service_time = t - self.seat_time
        if self.alert_raised_at is not None:
            self._log(t, "alert_closed", source=source,
                      first_service_time=self.first_service_time,
                      response_time=self.first_service_time)
            self.alert_raised_at = None
        else:
            self._log(t, "served", source=source,
                      first_service_time=self.first_service_time)

    def pos_order_opened(self, t: float) -> list[dict]:
        """POS event 'order opened for table N' cancels the timer, like a
        waiter visit. Only acts while the table is waiting or alerting."""
        before = len(self.events)
        if self.state in ("OCCUPIED_WAITING", "ALERT_UNATTENDED"):
            self._serve(t, source="pos_order_opened")
        return self.events[before:]

    @property
    def waiting_seconds(self) -> float | None:
        if self.state in ("OCCUPIED_WAITING", "ALERT_UNATTENDED") \
                and self.seat_time is not None:
            return None  # caller supplies `now`; see waiting_at()
        return None

    def waiting_at(self, now: float) -> float | None:
        if self.seat_time is None:
            return None
        return now - self.seat_time

    @property
    def is_occupied(self) -> bool:
        return self.state in ("OCCUPIED_WAITING", "ALERT_UNATTENDED",
                              "OCCUPIED_SERVED")

    @property
    def is_unattended(self) -> bool:
        return self.state == "ALERT_UNATTENDED"

    def escalated(self, now: float) -> bool:
        return (self.state == "ALERT_UNATTENDED"
                and self.alert_raised_at is not None
                and now - self.alert_raised_at >= ESCALATE_AFTER_SECONDS)
