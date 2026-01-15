from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CameraEdge:
    src: str
    dst: str
    # Optional time window. If not provided, the edge is time-agnostic.
    min_s: float | None = None
    max_s: float | None = None


class CameraNetwork:
    """Small helper to describe allowed camera-to-camera transitions.

    The goal is to improve multi-camera ReID by *gating* impossible matches
    using time + topology.

    If no edges are configured, the network is considered "open" and allows
    all transitions (backward compatible).
    """

    def __init__(
        self,
        edges: list[CameraEdge],
        *,
        default_max_gap_s: float | None = None,
        allow_same_camera_match: bool = True,
    ) -> None:
        self.edges = edges
        self.default_max_gap_s = default_max_gap_s
        self.allow_same_camera_match = allow_same_camera_match

        self._adj: dict[str, list[CameraEdge]] = {}
        self._rev_adj: dict[str, list[CameraEdge]] = {}
        for e in edges:
            self._adj.setdefault(e.src, []).append(e)
            self._rev_adj.setdefault(e.dst, []).append(e)

    @property
    def is_open(self) -> bool:
        return len(self.edges) == 0

    def allowed_transition(self, prev_camera: str | None, new_camera: str | None, dt_s: float | None) -> bool:
        if prev_camera is None or new_camera is None:
            return True

        prev_camera = str(prev_camera)
        new_camera = str(new_camera)

        if prev_camera == new_camera:
            return bool(self.allow_same_camera_match)

        if self.is_open:
            return True

        # If we don't know dt (missing sync), do not block transitions.
        if dt_s is None:
            dt_s = None

        try:
            dt_s_val = float(dt_s) if dt_s is not None else None
        except Exception:
            return True

        # Optional global max gap (e.g. ignore matches after 10+ minutes)
        if dt_s_val is not None and self.default_max_gap_s is not None and dt_s_val > float(self.default_max_gap_s):
            return False

        for e in self._adj.get(prev_camera, []):
            if e.dst != new_camera:
                continue

            # Time-agnostic edge: allow regardless of dt.
            if e.min_s is None and e.max_s is None:
                return True

            # Time-aware edge: only apply if we have dt.
            if dt_s_val is None:
                return True

            min_s = float(e.min_s) if e.min_s is not None else 0.0
            max_s = float(e.max_s) if e.max_s is not None else float("inf")
            if min_s <= dt_s_val <= max_s:
                return True

        return False

    def neighbors_out(self, camera_id: str) -> list[str]:
        """List cameras reachable from camera_id (outgoing edges)."""
        camera_id = str(camera_id)
        if self.is_open:
            return []
        return [e.dst for e in self._adj.get(camera_id, [])]

    def neighbors_in(self, camera_id: str) -> list[str]:
        """List cameras that can lead to camera_id (incoming edges)."""
        camera_id = str(camera_id)
        if self.is_open:
            return []
        return [e.src for e in self._rev_adj.get(camera_id, [])]

    def are_adjacent(self, a: str, b: str) -> bool:
        """True if a and b are connected by at least one edge (any direction)."""
        if self.is_open:
            return True
        a = str(a)
        b = str(b)
        return (b in self.neighbors_out(a)) or (a in self.neighbors_out(b))

    @staticmethod
    def load(path: str | Path) -> CameraNetwork:
        path = Path(path)
        if not path.exists():
            return CameraNetwork([])

        raw: dict[str, Any]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return CameraNetwork([])

        default_max_gap_s = raw.get("default_max_gap_s")
        allow_same_camera_match = raw.get("allow_same_camera_match", True)

        edges: list[CameraEdge] = []
        for item in raw.get("edges", []) or []:
            try:
                src = str(item["from"])
                dst = str(item["to"])
                min_s_raw = item.get("min_s", None)
                max_s_raw = item.get("max_s", None)

                min_s = float(min_s_raw) if min_s_raw is not None else None
                max_s = float(max_s_raw) if max_s_raw is not None else None

                edges.append(CameraEdge(src=src, dst=dst, min_s=min_s, max_s=max_s))
            except Exception:
                continue

        try:
            default_max_gap_s = float(default_max_gap_s) if default_max_gap_s is not None else None
        except Exception:
            default_max_gap_s = None

        return CameraNetwork(
            edges,
            default_max_gap_s=default_max_gap_s,
            allow_same_camera_match=bool(allow_same_camera_match),
        )
