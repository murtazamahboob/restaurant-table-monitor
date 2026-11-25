"""People: tracks, staff-vs-customer classification, zone assignment.

The blueprint's pipeline is YOLO + ByteTrack + a uniform-colour staff
classifier voted over 15 frames. This module is the offline, deterministic
equivalent: it consumes per-frame observations (foot point + a uniform
score in [0, 1]) and produces stable tracks with a voted role. No video is
stored and no faces are used anywhere — privacy by construction.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .geometry import Point, Polygon, point_in_polygon

STAFF_VOTE_FRAMES = 15
STAFF_VOTE_THRESHOLD = 0.6


@dataclass
class Observation:
    """One per-frame observation of one tracked person."""

    t: float
    person_id: str
    foot: Point
    uniform_score: float  # 0 = plain clothes, 1 = staff uniform colour/pattern


@dataclass
class Person:
    person_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=STAFF_VOTE_FRAMES))
    last_t: float = 0.0
    last_foot: Point = (0.0, 0.0)

    def observe(self, obs: Observation) -> None:
        self.history.append(obs.uniform_score)
        self.last_t = obs.t
        self.last_foot = obs.foot

    @property
    def is_staff(self) -> bool:
        """Staff only when the 15-frame vote says so; undecided -> customer."""
        if len(self.history) < STAFF_VOTE_FRAMES:
            return False
        return sum(self.history) / len(self.history) >= STAFF_VOTE_THRESHOLD

    @property
    def role(self) -> str:
        return "staff" if self.is_staff else "customer"

    @property
    def vote(self) -> float:
        if not self.history:
            return 0.0
        return sum(self.history) / len(self.history)


class Tracker:
    """Keeps one Person per id; drops tracks silent for more than 5 s
    (a ByteTrack-style keep-alive at 5-10 fps)."""

    def __init__(self, stale_after: float = 5.0) -> None:
        self.people: dict[str, Person] = {}
        self.stale_after = stale_after

    def observe(self, obs: Observation) -> Person:
        person = self.people.get(obs.person_id)
        if person is None:
            person = Person(person_id=obs.person_id)
            self.people[obs.person_id] = person
        person.observe(obs)
        return person

    def prune(self, now: float) -> list[str]:
        gone = [pid for pid, p in self.people.items()
                if now - p.last_t > self.stale_after]
        for pid in gone:
            del self.people[pid]
        return gone

    def in_zone(self, polygon: Polygon, now: float,
                role: str | None = None) -> list[Person]:
        """People whose last foot point is inside ``polygon``."""
        out = []
        for person in self.people.values():
            if role is not None and person.role != role:
                continue
            if point_in_polygon(person.last_foot, polygon):
                out.append(person)
        return out
