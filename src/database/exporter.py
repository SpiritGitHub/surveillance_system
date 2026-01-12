import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def export_personnes_from_trajectories(
    trajectories_dir: str | Path = "data/trajectories",
    output_csv: str | Path = "database/personnes.csv",
) -> dict[str, Any]:
    """Build a global person table from trajectories.

    Groups by global_id when present, otherwise keeps per-track rows.
    """
    trajectories_dir = Path(trajectories_dir)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    persons: dict[str, dict[str, Any]] = {}

    def get_person_key(video_id: str, track_id: str, global_id: Any) -> str:
        if global_id is None:
            return f"track::{video_id}::{track_id}"
        return f"global::{int(global_id)}"

    for jf in trajectories_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        video_id = str(data.get("video_id") or jf.stem)
        for trk in data.get("trajectories", []) or []:
            cls = trk.get("class_name")
            # backward compatible: missing class_name => treat as person
            if cls is not None and cls != "person":
                continue

            track_id = str(trk.get("track_id"))
            global_id = trk.get("global_id")
            try:
                global_id = int(global_id) if global_id is not None else None
            except Exception:
                global_id = None

            frames = trk.get("frames") or []
            t_sync_vals = [_safe_float(fr.get("t_sync")) for fr in frames]
            t_sync_vals = [t for t in t_sync_vals if t is not None]
            if t_sync_vals:
                t_first = min(t_sync_vals)
                t_last = max(t_sync_vals)
            else:
                t_first = None
                t_last = None

            key = get_person_key(video_id, track_id, global_id)
            row = persons.get(key)
            if row is None:
                row = {
                    "person_id": (str(global_id) if global_id is not None else ""),
                    "key": key,
                    "first_seen_t_sync": t_first,
                    "last_seen_t_sync": t_last,
                    "cameras": set([video_id]),
                    "first_camera": video_id,
                    "last_camera": video_id,
                    "tracks": set([f"{video_id}::{track_id}"]),
                    "tracks_count": 1,
                    "frames_count": len(frames),
                }
                persons[key] = row
            else:
                row["cameras"].add(video_id)
                row["tracks"].add(f"{video_id}::{track_id}")
                row["frames_count"] += len(frames)

                if t_first is not None and (row["first_seen_t_sync"] is None or t_first < row["first_seen_t_sync"]):
                    row["first_seen_t_sync"] = t_first
                    row["first_camera"] = video_id
                if t_last is not None and (row["last_seen_t_sync"] is None or t_last > row["last_seen_t_sync"]):
                    row["last_seen_t_sync"] = t_last
                    row["last_camera"] = video_id

    # finalize
    rows = []
    for row in persons.values():
        row["tracks_count"] = len(row["tracks"])
        rows.append(
            {
                "person_id": row["person_id"],
                "key": row["key"],
                "first_seen_t_sync": "" if row["first_seen_t_sync"] is None else f"{row['first_seen_t_sync']:.3f}",
                "last_seen_t_sync": "" if row["last_seen_t_sync"] is None else f"{row['last_seen_t_sync']:.3f}",
                "first_camera": row["first_camera"],
                "last_camera": row["last_camera"],
                "cameras": "|".join(sorted(row["cameras"])),
                "tracks_count": row["tracks_count"],
                "frames_count": row["frames_count"],
            }
        )

    # stable ordering: global ids first, then track keys
    def sort_key(r: dict[str, Any]):
        pid = r.get("person_id")
        if pid:
            try:
                return (0, int(pid))
            except Exception:
                return (0, pid)
        return (1, r.get("key") or "")

    rows.sort(key=sort_key)

    headers = [
        "person_id",
        "key",
        "first_seen_t_sync",
        "last_seen_t_sync",
        "first_camera",
        "last_camera",
        "cameras",
        "tracks_count",
        "frames_count",
    ]

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)

    return {
        "output": str(output_csv).replace("\\", "/"),
        "rows": len(rows),
        "unique_global_persons": len([r for r in rows if r.get("person_id")]),
    }


def export_evenements_from_events_jsonl(
    events_jsonl: str | Path,
    output_csv: str | Path = "database/evenements.csv",
    run_id: str | None = None,
) -> dict[str, Any]:
    events_jsonl = Path(events_jsonl)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not events_jsonl.exists():
        # still ensure header exists
        if output_csv.exists() and output_csv.stat().st_size > 0:
            return {"output": str(output_csv).replace("\\", "/"), "rows_appended": 0}

        headers = [
            "event_uid",
            "run_id",
            "timestamp",
            "event_type",
            "video_id",
            "track_id",
            "class_name",
            "global_id",
            "zone_id",
            "duration",
            "frame_id",
            "t",
            "t_sync",
            "prev_camera",
            "next_camera",
        ]
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=headers).writeheader()
        return {"output": str(output_csv).replace("\\", "/"), "rows_appended": 0}

    # load existing event_uids to avoid duplicates
    existing_uids = set()
    if output_csv.exists() and output_csv.stat().st_size > 0:
        try:
            with open(output_csv, "r", encoding="utf-8") as f:
                rdr = csv.DictReader(f)
                for r in rdr:
                    uid = r.get("event_uid")
                    if uid:
                        existing_uids.add(uid)
        except Exception:
            existing_uids = set()

    # parse events
    events: list[dict[str, Any]] = []
    with open(events_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue

    headers = [
        "event_uid",
        "run_id",
        "timestamp",
        "event_type",
        "video_id",
        "track_id",
        "class_name",
        "global_id",
        "zone_id",
        "duration",
        "frame_id",
        "t",
        "t_sync",
        "prev_camera",
        "next_camera",
    ]

    # if file empty create header
    if not output_csv.exists() or output_csv.stat().st_size == 0:
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=headers).writeheader()

    appended = 0
    with open(output_csv, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        for e in events:
            vid = e.get("video_id")
            tid = e.get("track_id")
            et = e.get("event_type")
            zid = e.get("zone_id")
            fid = e.get("frame_id")
            rid = run_id or ""
            uid = f"{rid}::{vid}::{tid}::{et}::{zid}::{fid}"
            if uid in existing_uids:
                continue

            prev_cam = e.get("prev_camera")
            next_cam = e.get("next_camera")
            w.writerow(
                {
                    "event_uid": uid,
                    "run_id": rid,
                    "timestamp": e.get("timestamp") or "",
                    "event_type": et or "",
                    "video_id": vid or "",
                    "track_id": tid or "",
                    "class_name": e.get("class_name") or "",
                    "global_id": e.get("global_id") if e.get("global_id") is not None else "",
                    "zone_id": zid or "",
                    "duration": e.get("duration") if e.get("duration") is not None else "",
                    "frame_id": fid if fid is not None else "",
                    "t": e.get("t") if e.get("t") is not None else "",
                    "t_sync": e.get("t_sync") if e.get("t_sync") is not None else "",
                    "prev_camera": prev_cam.get("video_id") if isinstance(prev_cam, dict) else "",
                    "next_camera": next_cam.get("video_id") if isinstance(next_cam, dict) else "",
                }
            )
            existing_uids.add(uid)
            appended += 1

    return {
        "output": str(output_csv).replace("\\", "/"),
        "rows_appended": appended,
        "events_file": str(events_jsonl).replace("\\", "/"),
    }


def export_classes_per_video(
    per_video_stats: dict[str, dict[str, Any]],
    output_csv: str | Path = "database/classes.csv",
    run_id: str | None = None,
) -> dict[str, Any]:
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    # build rows
    rows = []
    for video_id, st in per_video_stats.items():
        ubc = st.get("unique_by_class") or {}
        for cls, n in ubc.items():
            try:
                n_int = int(n)
            except Exception:
                continue
            rows.append(
                {
                    "run_id": run_id or "",
                    "video_id": video_id,
                    "class_name": cls,
                    "unique_tracks": n_int,
                }
            )

    headers = ["run_id", "video_id", "class_name", "unique_tracks"]

    # overwrite (this is per-run and small)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)

    return {"output": str(output_csv).replace("\\", "/"), "rows": len(rows)}


def export_classes_from_trajectories(
    trajectories_dir: str | Path = "data/trajectories",
    output_csv: str | Path = "database/classes.csv",
    run_id: str | None = None,
) -> dict[str, Any]:
    """Fallback export when no `per_video_stats` is available.

    Counts unique track_ids per (video_id, class_name) by scanning trajectories JSON.
    """
    trajectories_dir = Path(trajectories_dir)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    counts: dict[tuple[str, str], set[str]] = defaultdict(set)

    for jf in trajectories_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        video_id = str(data.get("video_id") or jf.stem)
        for trk in data.get("trajectories", []) or []:
            cls = trk.get("class_name")
            if cls is None:
                cls = "person"  # backward-compatible
            tid = trk.get("track_id")
            if tid is None:
                continue
            counts[(video_id, str(cls))].add(str(tid))

    rows = []
    for (video_id, cls), tids in sorted(counts.items(), key=lambda x: (x[0][0], x[0][1])):
        rows.append(
            {
                "run_id": run_id or "",
                "video_id": video_id,
                "class_name": cls,
                "unique_tracks": len(tids),
            }
        )

    headers = ["run_id", "video_id", "class_name", "unique_tracks"]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)

    return {"output": str(output_csv).replace("\\", "/"), "rows": len(rows), "source": "trajectories"}


def export_database(
    trajectories_dir: str | Path,
    events_jsonl: str | Path,
    per_video_stats: dict[str, dict[str, Any]],
    run_id: str,
    out_dir: str | Path = "database",
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    persons_info = export_personnes_from_trajectories(trajectories_dir, out_dir / "personnes.csv")
    events_info = export_evenements_from_events_jsonl(events_jsonl, out_dir / "evenements.csv", run_id=run_id)
    if per_video_stats:
        classes_info = export_classes_per_video(per_video_stats, out_dir / "classes.csv", run_id=run_id)
    else:
        classes_info = export_classes_from_trajectories(trajectories_dir, out_dir / "classes.csv", run_id=run_id)

    return {
        "personnes": persons_info,
        "evenements": events_info,
        "classes": classes_info,
    }
