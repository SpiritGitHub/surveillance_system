import json
import logging
from pathlib import Path
from collections import defaultdict
import sys


from src.zones.zone_manager import ZoneManager

logger = logging.getLogger("GlobalAnalysisV")

class GlobalAnalyzer:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.traj_dir = self.data_dir / "trajectories"
        # Events are written outside data/ (project convention)
        self.events_dir = Path("outputs") / "events"
        self.stories = {} # global_id -> Story object
        # Load zones from the same data_dir so DashboardV stays consistent.
        self.zone_manager = ZoneManager(zones_file=str(self.data_dir / "zones_interdites.json"))

    def _load_latest_events(self) -> list[dict]:
        """Load the latest events_*.jsonl file if available."""
        if not self.events_dir.exists():
            return []

        candidates = list(self.events_dir.glob("events_*.jsonl"))
        if not candidates:
            return []

        try:
            latest = max(candidates, key=lambda p: p.stat().st_mtime)
        except Exception:
            latest = sorted(candidates)[-1]

        events: list[dict] = []
        try:
            with open(latest, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            return []

        return events

    def load_data(self):
        """Loads all trajectory JSONs and organizes data by global_id."""
        json_files = list(self.traj_dir.glob("*.json"))
        if not json_files:
            logger.warning("No trajectory files found.")
            return

        print(f"[GlobalAnalysis] Loading {len(json_files)} trajectory files...")

        # 1. Aggregate all track segments by global_id
        all_segments = defaultdict(list) # global_id -> list of segments

        tracks_with_global_id = 0

        def _safe_float(v):
            try:
                if v is None:
                    return None
                return float(v)
            except Exception:
                return None

        for jf in json_files:
            try:
                with open(jf, "r") as f:
                    data = json.load(f)
                
                video_id = data["video_id"]
                # sync_offset isn't needed here because we use per-frame t_sync, but keep for compatibility.
                _ = data.get("sync_offset", 0.0)
                
                for track in data["trajectories"]:
                    gid = track.get("global_id")
                    if gid is None:
                        continue # Skip tracks without global ID (noise or unmatched)

                    # Normalize ids so DashboardV (which uses int when possible) matches analyzer keys.
                    try:
                        gid = int(gid)
                    except Exception:
                        pass
                    tracks_with_global_id += 1

                    frames = track.get("frames") or []
                    if not frames:
                        continue

                    start_time = _safe_float(frames[0].get("t_sync"))
                    if start_time is None:
                        start_time = _safe_float(frames[0].get("t"))
                    end_time = _safe_float(frames[-1].get("t_sync"))
                    if end_time is None:
                        end_time = _safe_float(frames[-1].get("t"))
                    if start_time is None or end_time is None:
                        continue
                    
                    # Create a segment summary
                    segment = {
                        "video_id": video_id,
                        "track_id": track["track_id"],
                        "start_time": start_time,
                        "end_time": end_time,
                        "alerts": [],
                    }
                    
                    all_segments[gid].append(segment)
                    
            except Exception as e:
                logger.error(f"Error loading {jf}: {e}")

        # 2. Build Stories
        print(f"[GlobalAnalysis] Building stories for {len(all_segments)} unique identities...")
        
        for gid, segments in all_segments.items():
            # Sort segments by time
            segments.sort(key=lambda x: x["start_time"])
            
            story = {
                "global_id": gid,
                "path": [], # Sequence of cameras: [(cam, start, end), ...]
                "alerts": [], # List of all alerts
                "total_duration": 0,
                "first_seen": segments[0]["start_time"],
                "last_seen": segments[-1]["end_time"]
            }
            
            for seg in segments:
                story["path"].append({
                    "camera": seg["video_id"],
                    "start": seg["start_time"],
                    "end": seg["end_time"]
                })
                # Aggregate alerts
                if seg["alerts"]:
                    # Dedup alerts? Or just list them?
                    # Let's just add them
                    for a in seg["alerts"]:
                        story["alerts"].append({
                            "camera": seg["video_id"],
                            "time": a["time"],
                            "zone": a.get("zone"),
                            "zone_id": a.get("zone_id"),
                        })
            
            self.stories[gid] = story

        # Load alerts from latest events file (fast, and already enriched with global_id/zone_name).
        events = self._load_latest_events()
        if events:
            by_gid: dict[object, list[dict]] = defaultdict(list)
            for e in events:
                gid = e.get("global_id")
                if gid is None:
                    continue
                try:
                    gid = int(gid)
                except Exception:
                    pass
                by_gid[gid].append(e)

            for gid, evs in by_gid.items():
                story = self.stories.get(gid)
                if not story:
                    continue
                for e in evs:
                    t_sync = _safe_float(e.get("t_sync"))
                    if t_sync is None:
                        continue
                    story["alerts"].append(
                        {
                            "camera": e.get("video_id"),
                            "time": t_sync,
                            "zone": e.get("zone_name") or e.get("zone_id"),
                            "zone_id": e.get("zone_id"),
                            "event_type": e.get("event_type"),
                        }
                    )

            # Sort alerts by time for display
            for story in self.stories.values():
                story["alerts"].sort(key=lambda a: (a.get("time") if a.get("time") is not None else float("inf")))

        if tracks_with_global_id == 0:
            print(
                "[GlobalAnalysis] INFO: aucun global_id trouvé dans data/trajectories/*.json. "
                "Le dashboard peut afficher les TID (ids locaux), mais pas les GID. "
                "Lancez d'abord `python main_v.py` (sans --dashboard-only) pour exécuter le global matching."
            )

    def get_story(self, global_id):
        return self.stories.get(global_id)

    def get_all_stories(self):
        return self.stories

if __name__ == "__main__":
    analyzer = GlobalAnalyzer()
    analyzer.load_data()
    # Print some sample stories
    for gid, story in list(analyzer.stories.items())[:5]:
        print(f"ID {gid}: Seen from {story['first_seen']:.1f}s to {story['last_seen']:.1f}s")
        for step in story["path"]:
            print(f"  -> {step['camera']} ({step['start']:.1f}s - {step['end']:.1f}s)")
