"""Privacy-first frame handling: faces are blurred, no video is stored.

Frames are processed in memory only — the engine never writes a frame to
disk, and only events (table id, state, timestamps) are logged. ``blur``
applies a plain box blur to each face region of a NumPy frame; everything
outside the boxes is returned bit-identical.
"""

from __future__ import annotations

import numpy as np


def blur_faces(frame: np.ndarray, boxes: list[tuple[int, int, int, int]],
               radius: int = 3) -> np.ndarray:
    """Box-blur each (x, y, w, h) face region in-place on a copy.

    ``radius`` is the blur kernel half-width in pixels. A uniform region
    stays uniform; a sharp edge inside the box is smoothed.
    """
    out = frame.copy()
    h, w = frame.shape[:2]
    for (x, y, bw, bh) in boxes:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(w, x + bw), min(h, y + bh)
        if x1 <= x0 or y1 <= y0:
            continue
        region = out[y0:y1, x0:x1].astype(np.float64)
        # Separable box blur: mean over a (2r+1) window, applied twice
        # (horizontal then vertical) via cumulative sums.
        k = 2 * radius + 1
        blurred = _box_blur_1d(_box_blur_1d(region, k, axis=1), k, axis=0)
        out[y0:y1, x0:x1] = np.clip(np.rint(blurred), 0, 255).astype(frame.dtype)
    return out


def _box_blur_1d(arr: np.ndarray, k: int, axis: int) -> np.ndarray:
    moved = np.moveaxis(arr, axis, 0)
    shape = moved.shape
    flat = moved.reshape(shape[0], -1)
    csum = np.vstack([np.zeros((1, flat.shape[1])), np.cumsum(flat, axis=0)])
    n = flat.shape[0]
    idx = np.arange(n)
    lo = np.maximum(0, idx - k // 2)
    hi = np.minimum(n, idx + k // 2 + 1)
    sums = csum[hi] - csum[lo]
    counts = (hi - lo)[:, None]
    out = (sums / counts).reshape(shape)
    return np.moveaxis(out, 0, axis)


class FrameStore:
    """Explicitly a no-op store: frames are never persisted.

    Keeping the class makes the guarantee greppable and testable — any
    future code that wants to save video has to touch this file.
    """

    stored_frames: int = 0

    def put(self, frame: np.ndarray) -> None:  # noqa: ARG002 - by design
        return None

    def __len__(self) -> int:
        return 0
