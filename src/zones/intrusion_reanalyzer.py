from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.alerts.alert_manager import AlertManager
from src.zones.zone_manager import ZoneManager


def reanalyze_intrusions_from_trajectories(
    *,
    trajectories_dir: str | Path = "data/trajectories",
    zones_file: str | Path = "data/zones_interdites.json",
    output_events_file: str | Path = "outputs/events/events_reanalysis.jsonl",
    class_name: str = "person",
) -> dict[str, Any]:
    """Recreate intrusion events by scanning saved trajectories against zones.

    This is a fast post-processing pass:
    - No YOLO, no tracking: uses `data/trajectories/*.json`.
    - Emits compact events (confirmed + ended) per track/zone interval.
    - Intrusion is confirmed immediately on first in-zone frame.

    Returns summary stats.
    """

    trajectories_dir = Path(trajectories_dir)
    zones_file = Path(zones_file)
    output_events_file = Path(output_events_file)
    output_events_file.parent.mkdir(parents=True, exist_ok=True)

    zm = ZoneManager(str(zones_file))
    am = AlertManager(str(output_events_file), min_duration=0.0)

    if not trajectories_dir.exists():
        return {
            "ok": False,
            "reason": "trajectories_dir_missing",
            "trajectories_dir": str(trajectories_dir).replace("\\", "/"),
        }

    videos_scanned = 0
    tracks_scanned = 0
    frames_scanned = 0

    # AlertManager doesn't expose counters; infer by file size deltas is unreliable.
    # We return scan stats; the report/events parser will summarize event counts.

    for jf in trajectories_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        video_id = str(data.get("video_id") or jf.stem)
        videos_scanned += 1

        for trk in data.get("trajectories", []) or []:
            trk_class = trk.get("class_name")
            if trk_class is None:
                trk_class = "person"  # backward-compatible
            if trk_class != class_name:
                continue

            track_id = trk.get("track_id")
            if track_id is None:
                continue
            track_id = str(track_id)

            frames = trk.get("frames") or []
            if not frames:
                continue

            tracks_scanned += 1

            last_t = None
            last_t_sync = None
            last_frame_id = None

            for fr in frames:
                bbox = fr.get("bbox")
                if not bbox:
                    continue

                try:
                    frame_id = int(fr.get("frame"))
                except Exception:
                    continue

                t = fr.get("t")
                t_sync = fr.get("t_sync")
                try:
                    t_val = float(t) if t is not None else float(frame_id)
                except Exception:
                    t_val = float(frame_id)

                try:
                    t_sync_val = float(t_sync) if t_sync is not None else None
                except Exception:
                    t_sync_val = None

                zone_ids = zm.check_bbox_all_zones(bbox, camera_id=video_id)
                am.update(
                    track_id=track_id,
                    zone_ids=zone_ids,
                    frame_time=t_val,
                    video_id=video_id,
                    frame_id=frame_id,
                    class_name=class_name,
                    t_sync=t_sync_val,
                )

                last_t = t_val
                last_t_sync = t_sync_val
                last_frame_id = frame_id
                frames_scanned += 1

            # Flush: ensure intrusions end when track disappears
            if last_t is not None and last_frame_id is not None:
                am.update(
                    track_id=track_id,
                    zone_ids=[],
                    frame_time=last_t,
                    video_id=video_id,
                    frame_id=last_frame_id,
                    class_name=class_name,
                    t_sync=last_t_sync,
                )

    return {
        "ok": True,
        "trajectories_dir": str(trajectories_dir).replace("\\", "/"),
        "zones_file": str(zones_file).replace("\\", "/"),
        "output_events_file": str(output_events_file).replace("\\", "/"),
        "videos_scanned": videos_scanned,
        "tracks_scanned": tracks_scanned,
        "frames_scanned": frames_scanned,
        "class_name": class_name,
        "min_duration": 0.0,
        "note": "Events are emitted as confirmed/ended intervals (not per frame).",
    }
