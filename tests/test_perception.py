"""Tests for perception: geometry, staff vote, surface smoothing."""

from tablemonitor.geometry import foot_point, point_in_polygon, rect_polygon
from tablemonitor.people import Observation, Person, Tracker
from tablemonitor.surface import SurfaceClassifier, SurfaceObservation


def test_point_in_polygon_inside_outside_and_edge():
    poly = rect_polygon(0, 0, 10, 6)
    assert point_in_polygon((5, 3), poly) is True
    assert point_in_polygon((20, 3), poly) is False
    assert point_in_polygon((0, 3), poly) is True  # on the edge counts


def test_foot_point_is_bottom_centre():
    assert foot_point((10, 20, 4, 8)) == (12.0, 28.0)


def test_staff_vote_needs_15_frames():
    person = Person(person_id="s1")
    for i in range(14):
        person.observe(Observation(t=float(i), person_id="s1",
                                   foot=(1, 1), uniform_score=0.95))
    assert person.is_staff is False
    person.observe(Observation(t=14.0, person_id="s1", foot=(1, 1),
                               uniform_score=0.95))
    assert person.is_staff is True
    assert person.role == "staff"


def test_mixed_uniform_votes_stay_customer():
    person = Person(person_id="c1")
    for i in range(15):
        person.observe(Observation(t=float(i), person_id="c1",
                                   foot=(1, 1), uniform_score=0.4))
    assert person.is_staff is False
    assert person.vote == 0.4


def test_tracker_zone_assignment_by_role():
    tracker = Tracker()
    poly = rect_polygon(0, 0, 10, 10)
    for i in range(15):
        tracker.observe(Observation(t=float(i), person_id="staff1",
                                    foot=(5, 5), uniform_score=0.95))
        tracker.observe(Observation(t=float(i), person_id="cust1",
                                    foot=(5, 5), uniform_score=0.05))
    assert [p.person_id for p in tracker.in_zone(poly, 15.0, role="staff")] == ["staff1"]
    assert [p.person_id for p in tracker.in_zone(poly, 15.0, role="customer")] == ["cust1"]
    assert len(tracker.in_zone(poly, 15.0)) == 2
    assert tracker.in_zone(rect_polygon(50, 50, 5, 5), 15.0) == []


def test_surface_dirty_score_threshold():
    obs = SurfaceObservation(t=0, table_id="T1", clutter=0.9, spill=0.6, trash=0.5)
    assert obs.score() == 0.9 * 0.5 + 0.6 * 0.3 + 0.5 * 0.2
    assert obs.raw_label() == "dirty"
    clean = SurfaceObservation(t=0, table_id="T1", clutter=0.05, spill=0.02, trash=0.0)
    assert clean.raw_label() == "clean"


def test_surface_state_flips_only_after_10s():
    clf = SurfaceClassifier("T1")
    dirty = lambda t: SurfaceObservation(t=t, table_id="T1", clutter=0.9,
                                         spill=0.6, trash=0.5)
    assert clf.observe(dirty(0)) == "clean"
    assert clf.observe(dirty(3)) == "clean"
    assert clf.observe(dirty(9)) == "clean"
    assert clf.observe(dirty(10)) == "dirty"


def test_surface_blip_does_not_flip():
    clf = SurfaceClassifier("T1")
    dirty = lambda t: SurfaceObservation(t=t, table_id="T1", clutter=0.9,
                                         spill=0.6, trash=0.5)
    clean = lambda t: SurfaceObservation(t=t, table_id="T1", clutter=0.05,
                                         spill=0.02, trash=0.0)
    clf.observe(dirty(0))
    clf.observe(dirty(3))
    assert clf.observe(clean(6)) == "clean"  # 5 s blip, back to clean
    assert clf.observe(dirty(9)) == "clean"  # pending restarts
    assert clf.observe(dirty(19)) == "dirty"
