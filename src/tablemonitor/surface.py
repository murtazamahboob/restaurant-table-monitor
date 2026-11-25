"""Table-surface classification: clean or dirty, with 10-second smoothing.

A crop of the table surface yields three features in [0, 1] — clutter
(plates, glasses), spill and trash — scored by a small fixed-weight rule
(no learned model, no camera needed for the offline replay). The reported
state only flips after the same answer has held for 10 seconds, so a
passing hand or a single noisy frame never flips a table.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SMOOTH_SECONDS = 10.0
DIRTY_THRESHOLD = 0.45
# score = 0.5 * clutter + 0.3 * spill + 0.2 * trash
WEIGHTS = (0.5, 0.3, 0.2)


@dataclass
class SurfaceObservation:
    t: float
    table_id: str
    clutter: float
    spill: float
    trash: float

    def score(self) -> float:
        return (WEIGHTS[0] * self.clutter + WEIGHTS[1] * self.spill
                + WEIGHTS[2] * self.trash)

    def raw_label(self) -> str:
        return "dirty" if self.score() >= DIRTY_THRESHOLD else "clean"


@dataclass
class SurfaceClassifier:
    """Smoothed clean/dirty state for one table."""

    table_id: str
    state: str = "clean"
    _pending: str = "clean"
    _pending_since: float = 0.0
    last_score: float = 0.0

    def observe(self, obs: SurfaceObservation) -> str:
        label = obs.raw_label()
        self.last_score = obs.score()
        if label == self.state:
            self._pending = label
            self._pending_since = obs.t
            return self.state
        if label != self._pending:
            self._pending = label
            self._pending_since = obs.t
        elif obs.t - self._pending_since >= SMOOTH_SECONDS:
            self.state = label
            self._pending = label
        return self.state

    @property
    def is_dirty(self) -> bool:
        return self.state == "dirty"
