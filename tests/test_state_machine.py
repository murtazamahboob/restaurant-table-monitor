"""Tests for the per-table state machine (blueprint section 6.4)."""

import pytest

from tablemonitor.state_machine import TableConfig, TableStateMachine


def _machine(timer: float = 300.0) -> TableStateMachine:
    return TableStateMachine(TableConfig(table_id="T1", service_timer=timer))


def _tick(m: TableStateMachine, t: float, customers: int = 0,
          staff: int = 0, surface: str = "clean"):
    return m.tick(t, customers, staff, surface)


def test_seating_needs_25s_and_timer_starts_at_first_seat():
    m = _machine()
    for t in range(25):
        _tick(m, float(t), customers=2)
    assert m.state == "OCCUPIED_WAITING"
    assert m.seat_time == 0.0


def test_brief_presence_does_not_seat():
    m = _machine()
    for t in range(10):
        _tick(m, float(t), customers=1)
    _tick(m, 10.0, customers=0)
    assert m.state == "EMPTY_CLEAN"
    assert m.seat_time is None


def test_waiter_visit_cancels_timer_and_logs_first_service():
    m = _machine()
    for t in range(25):
        _tick(m, float(t), customers=1)
    for t in range(25, 28):
        _tick(m, float(t), customers=1, staff=1)
    assert m.state == "OCCUPIED_SERVED"
    assert m.first_service_time == pytest.approx(27.0)


def test_unattended_alert_at_300s():
    m = _machine()
    for t in range(25):
        _tick(m, float(t), customers=1)
    for t in range(25, 301):
        events = _tick(m, float(t), customers=1)
    assert m.state == "ALERT_UNATTENDED"
    assert m.alert_raised_at == 300.0
    assert any(e["event"] == "unattended_alert" for e in events)


def test_late_waiter_closes_alert():
    m = _machine()
    for t in range(25):
        _tick(m, float(t), customers=1)
    for t in range(25, 301):
        _tick(m, float(t), customers=1)
    assert m.state == "ALERT_UNATTENDED"
    for t in range(301, 304):
        events = _tick(m, float(t), customers=1, staff=1)
    assert m.state == "OCCUPIED_SERVED"
    assert any(e["event"] == "alert_closed" for e in events)
    assert m.first_service_time == pytest.approx(303.0)


def test_pos_order_cancels_timer_like_a_waiter():
    m = _machine()
    for t in range(25):
        _tick(m, float(t), customers=1)
    events = m.pos_order_opened(60.0)
    assert m.state == "OCCUPIED_SERVED"
    assert m.first_service_time == pytest.approx(60.0)
    assert events[0]["source"] == "pos_order_opened"


def test_pos_does_nothing_on_empty_table():
    m = _machine()
    assert m.pos_order_opened(10.0) == []
    assert m.state == "EMPTY_CLEAN"


def test_leaving_dirty_then_cleaned_by_staff():
    m = _machine()
    for t in range(25):
        _tick(m, float(t), customers=1)
    for t in range(25, 28):
        _tick(m, float(t), customers=1, staff=1)
    assert m.state == "OCCUPIED_SERVED"
    for t in range(28, 73):
        _tick(m, float(t), customers=0, surface="dirty")
    assert m.state == "EMPTY_DIRTY"
    for t in range(73, 83):
        events = _tick(m, float(t), customers=0, staff=1, surface="clean")
    assert m.state == "EMPTY_CLEAN"
    assert any(e["event"] == "cleaned" for e in events)


def test_leaving_clean_goes_straight_to_empty_clean():
    m = _machine()
    for t in range(25):
        _tick(m, float(t), customers=1)
    for t in range(25, 28):
        _tick(m, float(t), customers=1, staff=1)
    for t in range(28, 73):
        _tick(m, float(t), customers=0, surface="clean")
    assert m.state == "EMPTY_CLEAN"


def test_clean_without_staff_does_not_finish():
    m = _machine()
    m.state = "EMPTY_DIRTY"
    for t in range(15):
        _tick(m, float(t), customers=0, staff=0, surface="clean")
    assert m.state == "EMPTY_DIRTY"


def test_per_table_timer_is_configurable():
    m = _machine(timer=120.0)
    for t in range(25):
        _tick(m, float(t), customers=1)
    for t in range(25, 121):
        _tick(m, float(t), customers=1)
    assert m.state == "ALERT_UNATTENDED"
