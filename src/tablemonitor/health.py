"""Camera health and drift checks.

- Frame-rate check: fewer frames than expected in a window -> DEGRADED.
- Frozen-frame check: identical consecutive frames (e.g. a stuck camera)
  beyond a threshold -> FROZEN.
- Surface drift: the mean dirty-score of the last N observations drifts
  away from the calibrated baseline by more than a threshold -> DRIFT,
  meaning the clean/dirty classifier needs re-calibration (new lighting,
  new tablecloths).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CameraHealth:
    expected_fps: float = 5.0
    frozen_limit: int = 10
    drift_threshold: float = 0.25
    baseline_dirty_mean: float = 0.20
    _frame_times: list[float] = field(default_factory=list)
    _last_frame_hash: int | None = None
    _frozen_run: int = 0
    _dirty_scores: list[float] = field(default_factory=list)

    def observe_frame(self, t: float, frame_hash: int) -> None:
        self._frame_times.append(t)
        if frame_hash == self._last_frame_hash:
            self._frozen_run += 1
        else:
            self._frozen_run = 0
        self._last_frame_hash = frame_hash

    def observe_surface_score(self, score: float) -> None:
        self._dirty_scores.append(score)
        if len(self._dirty_scores) > 200:
            self._dirty_scores.pop(0)

    def fps_in_window(self, now: float, window: float = 10.0) -> float:
        recent = [t for t in self._frame_times if now - t <= window]
        return len(recent) / window if window else 0.0

    def status(self, now: float) -> dict:
        fps = self.fps_in_window(now)
        drift = None
        if self._dirty_scores:
            drift = abs(sum(self._dirty_scores) / len(self._dirty_scores)
                        - self.baseline_dirty_mean)
        problems = []
        if fps < self.expected_fps * 0.5:
            problems.append("LOW_FPS")
        if self._frozen_run >= self.frozen_limit:
            problems.append("FROZEN")
        if drift is not None and drift > self.drift_threshold:
            problems.append("DRIFT")
        return {"fps": round(fps, 2), "frozen_run": self._frozen_run,
                "drift": None if drift is None else round(drift, 3),
                "status": "DEGRADED" if problems else "OK",
                "problems": problems}
