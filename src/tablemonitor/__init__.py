"""Restaurant Table Monitor — camera-based table state, service timers and
alerts, offline and deterministic. Pure NumPy + stdlib: no model, no API
key, no network, no real video. The replay uses a scripted synthetic
dining room; a real deployment swaps the observation source for a camera
pipeline (RTSP at 5-10 fps, detector + tracker) without changing the
state machine, alerts or dashboard.
"""

from __future__ import annotations

from .alerts import Alert, AlertEngine
from .dashboard import analytics, render_floor_map
from .engine import TableDef, VenueEngine
from .geometry import foot_point, point_in_polygon, rect_polygon
from .health import CameraHealth
from .people import Observation, Person, Tracker
from .pos import PosEvent, PushMessage, PushOutbox
from .privacy import FrameStore, blur_faces
from .replay import build_episodes, build_tables, run_replay
from .state_machine import TableConfig, TableStateMachine
from .surface import SurfaceClassifier, SurfaceObservation

__all__ = [
    "Alert", "AlertEngine", "analytics", "blur_faces", "build_episodes",
    "build_tables", "CameraHealth", "foot_point", "FrameStore",
    "Observation", "Person", "point_in_polygon", "PosEvent",
    "PushMessage", "PushOutbox", "rect_polygon", "render_floor_map",
    "run_replay", "SurfaceClassifier", "SurfaceObservation", "TableConfig",
    "TableDef", "TableStateMachine", "Tracker", "VenueEngine",
]

__version__ = "1.0.0"
