import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.camera_network import CameraNetwork


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


def _normalize_zone_name(name: str | None) -> str | None:
    if name is None:
        return None
    s = str(name).strip().lower()
    return s or None


def _load_zones(zones_file: Path) -> dict[str, dict[str, Any]]:
    """Load zones definition to enrich events with zone_name and support dedup."""
    if not zones_file.exists():
        return {}
    try:
        raw = json.loads(zones_file.read_text(encoding="utf-8"))
    except Exception:
        return {}

    zones: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for zid, z in raw.items():
            if not isinstance(z, dict):
                continue
            zones[str(zid)] = {
                "zone_id": str(z.get("zone_id") or zid),
                "name": z.get("name"),
                "camera_id": z.get("camera_id"),
                "description": z.get("description"),
            }
    return zones


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
    camera_network: CameraNetwork | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prev_app: TrackAppearance | None = None
    next_app: TrackAppearance | None = None

    incoming: set[str] | None = None
    outgoing: set[str] | None = None
    if camera_network is not None and not camera_network.is_open:
        try:
            incoming = set(camera_network.neighbors_in(event_video_id))
            outgoing = set(camera_network.neighbors_out(event_video_id))
        except Exception:
            incoming = None
            outgoing = None

    for app in appearances:
        if app.video_id == event_video_id:
            continue
        if incoming is not None and app.video_id not in incoming:
            continue
        if app.t_end_sync is not None and app.t_end_sync < event_t_sync:
            if prev_app is None or (prev_app.t_end_sync is None) or app.t_end_sync > prev_app.t_end_sync:
                prev_app = app

    for app in appearances:
        if app.video_id == event_video_id:
            continue
        if outgoing is not None and app.video_id not in outgoing:
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


def _dedup_overlapping_zone_events(
    events: list[dict[str, Any]],
    *,
    zones: dict[str, dict[str, Any]] | None,
    camera_network: CameraNetwork | None,
    time_window_s: float = 2.0,
) -> list[dict[str, Any]]:
    """Deduplicate events for the same physical zone seen by overlapping cameras.

    Heuristic (safe-by-default):
    - only if global_id + t_sync exist
    - same event_type
    - same normalized zone_name (preferred) else same zone_id
    - cameras must be adjacent in the configured camera_network (if provided and not open)
    - t_sync within a short window
    """

    def zone_key(e: dict[str, Any]) -> str | None:
        zid = e.get("zone_id")
        if zid is None:
            return None
        z = zones.get(str(zid)) if zones else None
        name = _normalize_zone_name(z.get("name")) if isinstance(z, dict) else None
        return name or str(zid)

    def is_adjacent(cam_a: str, cam_b: str) -> bool:
        if cam_a == cam_b:
            return True
        if camera_network is None:
            return False
        if camera_network.is_open:
            return False
        try:
            return camera_network.are_adjacent(cam_a, cam_b)
        except Exception:
            return False

    # Sort deterministically by sync time if available; keep original order as tie-breaker.
    indexed = list(enumerate(events))
    indexed.sort(key=lambda it: (_safe_float(it[1].get("t_sync")) if _safe_float(it[1].get("t_sync")) is not None else float("inf"), it[0]))

    out: list[dict[str, Any]] = []
    last_by_key: dict[tuple[str, str, str], int] = {}

    for _, e in indexed:
        gid = e.get("global_id")
        ev_type = e.get("event_type")
        t_sync = _safe_float(e.get("t_sync"))
        cam = e.get("video_id")
        zk = zone_key(e)

        if gid is None or ev_type is None or t_sync is None or cam is None or zk is None:
            out.append(e)
            continue

        key = (str(gid), str(ev_type), str(zk))
        prev_idx = last_by_key.get(key)

        if prev_idx is None:
            out.append(e)
            last_by_key[key] = len(out) - 1
            continue

        prev = out[prev_idx]
        prev_t = _safe_float(prev.get("t_sync"))
        prev_cam = prev.get("video_id")

        if prev_t is None or prev_cam is None:
            out.append(e)
            last_by_key[key] = len(out) - 1
            continue

        if abs(float(t_sync) - float(prev_t)) <= float(time_window_s) and is_adjacent(str(prev_cam), str(cam)):
            prev.setdefault("merged_from", []).append(
                {
                    "video_id": cam,
                    "track_id": e.get("track_id"),
                    "zone_id": e.get("zone_id"),
                    "t_sync": t_sync,
                    "frame_id": e.get("frame_id"),
                }
            )
            # Keep the earliest sync time as the representative.
            if float(t_sync) < float(prev_t):
                prev["t_sync"] = float(t_sync)
            continue

        out.append(e)
        last_by_key[key] = len(out) - 1

    # Restore original chronological-ish order by t_sync when possible.
    out.sort(key=lambda ev: (_safe_float(ev.get("t_sync")) if _safe_float(ev.get("t_sync")) is not None else float("inf")))
    return out


def enrich_events_with_global_ids(
    events_path: str | Path,
    trajectories_dir: str | Path = "data/trajectories",
    in_place: bool = True,
    *,
    camera_network_path: str | Path = "configs/camera_network.json",
    zones_file: str | Path = "data/zones_interdites.json",
    dedup_overlapping_zones: bool = True,
    dedup_time_window_s: float = 2.0,
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

    camera_network = CameraNetwork.load(camera_network_path)
    zones = _load_zones(Path(zones_file))

    events = _read_events_jsonl(events_path)
    track_map, appearances_by_gid = _load_trajectory_files(trajectories_dir)

    for e in events:
        vid = e.get("video_id")
        tid = e.get("track_id")
        t_sync = _safe_float(e.get("t_sync"))
        if not vid or not tid:
            continue

        # Add zone_name if possible (helps dashboards + dedup)
        zid = e.get("zone_id")
        if zid is not None:
            z = zones.get(str(zid))
            if isinstance(z, dict):
                if "zone_name" not in e and z.get("name") is not None:
                    e["zone_name"] = z.get("name")

        app = track_map.get((str(vid), str(tid)))
        if app is None:
            continue

        e["class_name"] = e.get("class_name") or app.class_name
        if app.global_id is not None:
            e["global_id"] = app.global_id

            if t_sync is not None:
                prev_cam, next_cam = _find_prev_next_camera(
                    appearances=appearances_by_gid.get(app.global_id, []),
                    event_video_id=str(vid),
                    event_t_sync=t_sync,
                    camera_network=camera_network,
                )
                e["prev_camera"] = prev_cam
                e["next_camera"] = next_cam

                # Also provide explicit candidate neighbors from the network.
                if camera_network is not None and not camera_network.is_open:
                    e["prev_camera_candidates"] = camera_network.neighbors_in(str(vid))
                    e["next_camera_candidates"] = camera_network.neighbors_out(str(vid))

        e["enriched"] = True

    if dedup_overlapping_zones:
        events = _dedup_overlapping_zone_events(
            events,
            zones=zones,
            camera_network=camera_network,
            time_window_s=float(dedup_time_window_s),
        )

    events_enriched = sum(1 for e in events if e.get("enriched"))
    events_with_gid = sum(1 for e in events if e.get("global_id") is not None)

    if in_place:
        _write_events_jsonl(events_path, events)

    return {
        "events_total": len(events),
        "events_enriched": events_enriched,
        "events_with_global_id": events_with_gid,
        "events_file": str(events_path).replace("\\", "/"),
        "trajectories_dir": str(trajectories_dir).replace("\\", "/"),
        "camera_network": str(Path(camera_network_path)).replace("\\", "/"),
        "zones_file": str(Path(zones_file)).replace("\\", "/"),
        "dedup_overlapping_zones": bool(dedup_overlapping_zones),
        "dedup_time_window_s": float(dedup_time_window_s),
    }
