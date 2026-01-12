import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _safe_read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = Counter()
    by_class = Counter()
    by_zone = Counter()
    by_video = Counter()

    for e in events:
        by_type[e.get("event_type") or "unknown"] += 1
        by_class[e.get("class_name") or "unknown"] += 1
        by_zone[e.get("zone_id") or "unknown"] += 1
        by_video[e.get("video_id") or "unknown"] += 1

    return {
        "total": len(events),
        "by_type": dict(by_type),
        "by_class": dict(by_class),
        "by_zone": dict(by_zone),
        "by_video": dict(by_video),
    }


def summarize_stats(per_video_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    unique_by_class_total = Counter()
    frames_total = 0
    total_detections = 0
    total_tracks = 0

    for _, st in per_video_stats.items():
        frames_total += int(st.get("frames_processed") or 0)
        total_detections += int(st.get("total_detections") or 0)
        total_tracks += int(st.get("total_tracks") or 0)

        ubc = st.get("unique_by_class") or {}
        for k, v in ubc.items():
            try:
                unique_by_class_total[k] += int(v)
            except Exception:
                continue

    return {
        "frames_processed_total": frames_total,
        "total_detections": total_detections,
        "total_tracks": total_tracks,
        "unique_tracks_sum_by_class": dict(unique_by_class_total),
    }


def compute_top_classes(per_video_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compute top classes using per-video stats (unique tracks per class)."""
    totals = Counter()
    per_video_counts = defaultdict(list)

    for _, st in per_video_stats.items():
        ubc = st.get("unique_by_class") or {}
        for cls, n in ubc.items():
            try:
                n_int = int(n)
            except Exception:
                continue
            totals[cls] += n_int
            per_video_counts[cls].append(n_int)

    averages = {
        cls: (sum(vals) / len(vals) if vals else 0.0)
        for cls, vals in per_video_counts.items()
    }

    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "most_tracked_class": top[0][0] if top else None,
        "totals_unique_tracks_by_class": dict(totals),
        "avg_unique_tracks_by_class": averages,
        "top5_by_unique_tracks": top[:5],
    }


def compute_global_ids_by_video(trajectories_dir: str | Path) -> dict[str, Any]:
    trajectories_dir = Path(trajectories_dir)
    per_video: dict[str, int] = {}
    total_set = set()

    for jf in trajectories_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue

        video_id = data.get("video_id")
        if not video_id:
            continue

        gids = set()
        for trk in data.get("trajectories", []) or []:
            cls = trk.get("class_name")
            if cls is not None and cls != "person":
                continue
            gid = trk.get("global_id")
            if gid is None:
                continue
            try:
                gid_int = int(gid)
            except Exception:
                continue
            gids.add(gid_int)
            total_set.add(gid_int)

        per_video[str(video_id)] = len(gids)

    return {
        "per_video": per_video,
        "total_unique_global_ids": len(total_set),
    }


def write_run_report(
    output_path: str | Path,
    run_info: dict[str, Any],
    per_video_stats: dict[str, dict[str, Any]],
    events_path: str | Path | None = None,
    global_matching_info: dict[str, Any] | None = None,
    trajectories_dir: str | Path | None = None,
) -> dict[str, Any]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "run": run_info,
        "videos": {
            "count": len(per_video_stats),
            "per_video": per_video_stats,
            "summary": summarize_stats(per_video_stats),
        },
        "top_classes": compute_top_classes(per_video_stats),
    }

    if events_path is not None:
        events_path = Path(events_path)
        events = _safe_read_jsonl(events_path)
        report["events"] = {
            "path": str(events_path).replace("\\", "/"),
            "summary": summarize_events(events),
        }

    if global_matching_info is not None:
        report["global_matching"] = global_matching_info

    if trajectories_dir is not None:
        report["global_ids"] = compute_global_ids_by_video(trajectories_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report
