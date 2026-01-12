import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrackAppearance:
    video_id: str
    track_id: str
    class_name: str | None
    global_id: int | None
    t_start_sync: float | None
    t_end_sync: float | None


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _read_events_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue
    return events


def _write_events_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _load_trajectory_files(trajectories_dir: Path) -> tuple[
    dict[tuple[str, str], TrackAppearance],
    dict[int, list[TrackAppearance]],
]:
    track_map: dict[tuple[str, str], TrackAppearance] = {}
    appearances_by_gid: dict[int, list[TrackAppearance]] = {}

    for traj_file in trajectories_dir.glob("*.json"):
        try:
            data = json.loads(traj_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        video_id = data.get("video_id")
        if not video_id:
            continue

        for trk in data.get("trajectories", []) or []:
            track_id = trk.get("track_id")
            if not track_id:
                continue

            class_name = trk.get("class_name")
            gid = trk.get("global_id")
            try:
                gid = int(gid) if gid is not None else None
            except Exception:
                gid = None

            frames = trk.get("frames") or []
            t_vals = [_safe_float(fr.get("t_sync")) for fr in frames]
            t_vals = [t for t in t_vals if t is not None]
            t_start = min(t_vals) if t_vals else None
            t_end = max(t_vals) if t_vals else None

            app = TrackAppearance(
                video_id=str(video_id),
                track_id=str(track_id),
                class_name=str(class_name) if class_name is not None else None,
                global_id=gid,
                t_start_sync=t_start,
                t_end_sync=t_end,
            )

            track_map[(app.video_id, app.track_id)] = app
            if gid is not None:
                appearances_by_gid.setdefault(gid, []).append(app)

    # sort appearances by time for fast prev/next lookup
    for gid, apps in appearances_by_gid.items():
        apps.sort(key=lambda a: (a.t_start_sync if a.t_start_sync is not None else float("inf")))

    return track_map, appearances_by_gid


def _find_prev_next_camera(
    appearances: list[TrackAppearance],
    event_video_id: str,
    event_t_sync: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prev_app: TrackAppearance | None = None
    next_app: TrackAppearance | None = None

    for app in appearances:
        if app.video_id == event_video_id:
            continue
        if app.t_end_sync is not None and app.t_end_sync < event_t_sync:
            if prev_app is None or (prev_app.t_end_sync is None) or app.t_end_sync > prev_app.t_end_sync:
                prev_app = app

    for app in appearances:
        if app.video_id == event_video_id:
            continue
        if app.t_start_sync is not None and app.t_start_sync > event_t_sync:
            if next_app is None or (next_app.t_start_sync is None) or app.t_start_sync < next_app.t_start_sync:
                next_app = app

    def _to_dict(app: TrackAppearance | None) -> dict[str, Any] | None:
        if app is None:
            return None
        return {
            "video_id": app.video_id,
            "track_id": app.track_id,
            "t_start_sync": app.t_start_sync,
            "t_end_sync": app.t_end_sync,
        }

    return _to_dict(prev_app), _to_dict(next_app)


def enrich_events_with_global_ids(
    events_path: str | Path,
    trajectories_dir: str | Path = "data/trajectories",
    in_place: bool = True,
) -> dict[str, Any]:
    """Enrich JSONL intrusion events with `global_id` and camera transitions.

    We do this AFTER global matching, by joining (video_id, track_id) -> global_id.

    Adds:
      - global_id (if found)
      - prev_camera / next_camera based on synchronized time (t_sync)

    Returns a small summary.
    """
    events_path = Path(events_path)
    trajectories_dir = Path(trajectories_dir)

    events = _read_events_jsonl(events_path)
    track_map, appearances_by_gid = _load_trajectory_files(trajectories_dir)

    enriched = 0
    with_gid = 0

    for e in events:
        vid = e.get("video_id")
        tid = e.get("track_id")
        t_sync = _safe_float(e.get("t_sync"))
        if not vid or not tid:
            continue

        app = track_map.get((str(vid), str(tid)))
        if app is None:
            continue

        e["class_name"] = e.get("class_name") or app.class_name
        if app.global_id is not None:
            e["global_id"] = app.global_id
            with_gid += 1

            if t_sync is not None:
                prev_cam, next_cam = _find_prev_next_camera(
                    appearances=appearances_by_gid.get(app.global_id, []),
                    event_video_id=str(vid),
                    event_t_sync=t_sync,
                )
                e["prev_camera"] = prev_cam
                e["next_camera"] = next_cam

        e["enriched"] = True
        enriched += 1

    if in_place:
        _write_events_jsonl(events_path, events)

    return {
        "events_total": len(events),
        "events_enriched": enriched,
        "events_with_global_id": with_gid,
        "events_file": str(events_path).replace("\\", "/"),
        "trajectories_dir": str(trajectories_dir).replace("\\", "/"),
    }
