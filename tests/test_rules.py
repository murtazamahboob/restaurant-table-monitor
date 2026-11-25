"""Tests for the alert engine, crowd rule, POS events and push outbox."""

from tablemonitor.alerts import AlertEngine
from tablemonitor.pos import PosEvent, PushOutbox


def test_unattended_alert_deduplicated_while_open():
    eng = AlertEngine()
    a1 = eng.open_unattended("T2", 300.0, waited=300.0)
    assert a1 is not None
    assert eng.open_unattended("T2", 310.0, waited=310.0) is None
    assert len(eng.open_alerts) == 1


def test_unattended_alert_can_reopen_after_close():
    eng = AlertEngine()
    eng.open_unattended("T2", 300.0, waited=300.0)
    closed = eng.close_unattended("T2", 400.0)
    assert closed is not None and closed.status == "closed"
    assert eng.open_unattended("T2", 700.0, waited=300.0) is not None


def test_escalation_after_two_more_minutes():
    eng = AlertEngine()
    eng.open_unattended("T2", 300.0, waited=300.0)
    assert eng.escalate(419.0) == []
    escalated = eng.escalate(420.0)
    assert len(escalated) == 1
    assert escalated[0].severity == "critical"
    assert eng.escalate(500.0) == []  # already critical, not re-escalated


def test_crowd_rule_fires_at_80_percent_and_two_dirty():
    eng = AlertEngine()
    alert = eng.check_crowd_rule(465.0, 10, 8, ["T5", "T7"])
    assert alert is not None
    assert alert.kind == "CLEAN_TABLES_NOW"
    assert alert.detail["tables"] == ["T5", "T7"]


def test_crowd_rule_needs_both_conditions():
    eng = AlertEngine()
    assert eng.check_crowd_rule(0.0, 10, 7, ["T5", "T7"]) is None  # 70% occupied
    assert eng.check_crowd_rule(0.0, 10, 8, ["T5"]) is None  # only 1 dirty
    assert eng.check_crowd_rule(0.0, 10, 8, []) is None


def test_crowd_rule_repeats_every_five_minutes():
    eng = AlertEngine()
    assert eng.check_crowd_rule(465.0, 10, 8, ["T5", "T7"]) is not None
    assert eng.check_crowd_rule(600.0, 10, 8, ["T5", "T7"]) is None
    assert eng.check_crowd_rule(765.0, 10, 8, ["T5", "T7"]) is not None


def test_crowd_rule_twenty_percent_dirty_also_fires():
    eng = AlertEngine()
    assert eng.check_crowd_rule(0.0, 10, 9, ["T5", "T7"]) is not None


def test_pos_event_parsing():
    ev = PosEvent.from_dict({"t": 90, "table": "T4", "kind": "order_opened"})
    assert ev.t == 90.0 and ev.table_id == "T4" and ev.kind == "order_opened"
    ev2 = PosEvent.from_dict({"t": 100, "table": "T1"})
    assert ev2.kind == "order_opened"


def test_push_outbox_fans_out_to_waiter_and_manager():
    outbox = PushOutbox()
    msgs = outbox.send_alert("A0001", "UNATTENDED_TABLE", "T2", 300.0, "warning")
    assert [m.channel for m in msgs] == ["waiter_phone", "telegram_manager"]
    assert "T2" in msgs[0].text and "5 minutes" in msgs[0].text
    assert len(outbox.for_alert("A0001")) == 2
