"""Tests for privacy (face blur, no video stored), the dashboard, camera
health, and the full lunch-rush replay."""

import numpy as np

from tablemonitor.dashboard import analytics, render_floor_map
from tablemonitor.health import CameraHealth
from tablemonitor.privacy import FrameStore, blur_faces
from tablemonitor.replay import run_replay


def test_blur_smooths_face_region_only():
    frame = np.zeros((20, 20), dtype=np.uint8)
    frame[:, 10:] = 255  # sharp vertical edge across the whole frame
    blurred = blur_faces(frame, [(5, 5, 10, 10)], radius=2)
    assert blurred.shape == frame.shape
    # Outside the box: bit-identical.
    assert np.array_equal(blurred[:5, :], frame[:5, :])
    assert np.array_equal(blurred[15:, :], frame[15:, :])
    assert np.array_equal(blurred[:, :5], frame[:, :5])
    # Inside the box the hard edge is gone: intermediate values appear.
    region = blurred[5:15, 5:15]
    assert any(0 < int(v) < 255 for v in region.flat)  # edge is smoothed
    assert not np.array_equal(region, frame[5:15, 5:15])


def test_blur_leaves_uniform_region_unchanged():
    frame = np.full((10, 10), 128, dtype=np.uint8)
    assert np.array_equal(blur_faces(frame, [(0, 0, 10, 10)]), frame)


def test_no_video_is_stored():
    store = FrameStore()
    store.put(np.zeros((4, 4), dtype=np.uint8))
    assert len(store) == 0
    assert store.stored_frames == 0


def test_floor_map_shows_states_and_alerts():
    tables = [{"id": "T1", "x": 0, "y": 0, "w": 64, "h": 48,
               "state": "ALERT_UNATTENDED", "capacity": 4, "waiting_s": 320},
              {"id": "T2", "x": 80, "y": 0, "w": 64, "h": 48,
               "state": "EMPTY_CLEAN", "capacity": 4, "waiting_s": None}]
    alerts = [{"kind": "UNATTENDED_TABLE", "table": "T1",
               "severity": "critical", "status": "open"}]
    html_doc = render_floor_map(tables, alerts)
    assert "T1" in html_doc and "ALERT UNATTENDED" in html_doc
    assert "waiting 320s" in html_doc
    assert "UNATTENDED_TABLE" in html_doc
    assert "no video is stored" in html_doc


def test_analytics_counts_service_times():
    events = [
        {"event": "seated", "first_service_time": None},
        {"event": "served", "first_service_time": 102.0},
        {"event": "served", "first_service_time": 452.0},
        {"event": "cleaned"},
    ]
    alerts = [{"kind": "UNATTENDED_TABLE"}, {"kind": "CLEAN_TABLES_NOW"}]
    result = analytics(events, alerts)
    assert result["seatings"] == 1
    assert result["first_service_mean_s"] == 277.0
    assert result["first_service_max_s"] == 452.0
    assert result["first_service_under_300s"] == 1
    assert result["unattended_alerts"] == 1
    assert result["tables_cleaned"] == 1


def test_camera_health_frozen_and_drift():
    health = CameraHealth()
    for i in range(12):
        health.observe_frame(float(i), frame_hash=42)
    status = health.status(11.0)
    assert "FROZEN" in status["problems"]
    health2 = CameraHealth()
    for _ in range(10):
        health2.observe_surface_score(0.9)
    assert "DRIFT" in health2.status(10.0)["problems"]


def test_camera_health_ok_when_frames_flow():
    health = CameraHealth()
    for i in range(60):
        health.observe_frame(float(i) * 0.2, frame_hash=i)
    assert health.status(12.0)["status"] == "OK"


def test_full_replay_hits_every_blueprint_rule():
    report = run_replay()
    m = report["metrics"]
    assert m["seated_detection"] == "10/10"
    assert m["waiter_visit_recall"] == 1.0
    assert m["waiter_visit_precision"] == 1.0
    assert m["pos_served"] == 1
    assert m["surface_accuracy"] == 1.0
    assert m["unattended_alerts"] == 1
    assert m["clean_tables_now_alerts"] >= 1
    assert m["tables_cleaned"] >= 1
    assert m["first_service_max_s"] > 300  # T2's late service is logged
    assert any(a["severity"] == "critical"
               for a in report["alerts"])  # T2 escalated
    assert report["final_states"]["T5"] == "EMPTY_DIRTY"  # never cleaned
    assert report["final_states"]["T3"] == "EMPTY_CLEAN"  # cleaned by staff
    assert len(report["push_messages"]) >= 4  # waiter phone + manager per alert
