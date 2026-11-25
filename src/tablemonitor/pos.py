"""POS integration and waiter-phone push alerts.

POS: the most accurate cancel signal is the POS event "order opened for
table N". Events arrive as plain dicts (JSON from a POS webhook or a CSV
import) — no POS vendor SDK, no network. A waiter visit is the visual
proxy; a POS event is the authoritative one, and either cancels the timer.

Push: alerts are fanned out to a simulated waiter-phone outbox (and a
manager Telegram channel) as JSON-serialisable messages. In production the
outbox is the boundary a real push/Telegram sender reads from.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PosEvent:
    t: float
    table_id: str
    kind: str = "order_opened"  # order_opened | bill_requested | paid

    @classmethod
    def from_dict(cls, raw: dict) -> "PosEvent":
        return cls(t=float(raw["t"]), table_id=str(raw["table"]),
                   kind=str(raw.get("kind", "order_opened")))


@dataclass
class PushMessage:
    channel: str  # waiter_phone | telegram_manager
    alert_id: str
    text: str
    t: float

    def to_dict(self) -> dict:
        return {"channel": self.channel, "alert_id": self.alert_id,
                "text": self.text, "t": self.t}


class PushOutbox:
    """Outbox for waiter-phone and manager alerts."""

    def __init__(self) -> None:
        self.sent: list[PushMessage] = []

    def send(self, channel: str, alert_id: str, text: str, t: float) -> PushMessage:
        msg = PushMessage(channel=channel, alert_id=alert_id, text=text, t=t)
        self.sent.append(msg)
        return msg

    def send_alert(self, alert_id: str, kind: str, table_id: str | None,
                   t: float, severity: str) -> list[PushMessage]:
        if kind == "UNATTENDED_TABLE":
            text = (f"[{severity.upper()}] Table {table_id} has waited "
                    f"over 5 minutes with no waiter visit.")
        else:
            text = (f"[{severity.upper()}] Dining room crowded and tables "
                    f"need cleaning now.")
        return [self.send("waiter_phone", alert_id, text, t),
                self.send("telegram_manager", alert_id, text, t)]

    def for_alert(self, alert_id: str) -> list[PushMessage]:
        return [m for m in self.sent if m.alert_id == alert_id]
