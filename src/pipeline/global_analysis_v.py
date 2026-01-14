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
        self.stories = {} # global_id -> Story object
        # Load zones from the same data_dir so DashboardV stays consistent.
        self.zone_manager = ZoneManager(zones_file=str(self.data_dir / "zones_interdites.json"))

    def load_data(self):
        """Loads all trajectory JSONs and organizes data by global_id."""
        json_files = list(self.traj_dir.glob("*.json"))
        if not json_files:
            logger.warning("No trajectory files found.")
            return

        print(f"[GlobalAnalysis] Loading {len(json_files)} trajectory files...")

        # 1. Aggregate all track segments by global_id
        all_segments = defaultdict(list) # global_id -> list of segments

        for jf in json_files:
            try:
                with open(jf, "r") as f:
                    data = json.load(f)
                
                video_id = data["video_id"]
                sync_offset = data.get("sync_offset", 0.0)
                
                for track in data["trajectories"]:
                    gid = track.get("global_id")
                    if gid is None:
                        continue # Skip tracks without global ID (noise or unmatched)
                    
                    # Create a segment summary
                    segment = {
                        "video_id": video_id,
                        "track_id": track["track_id"],
                        "start_time": track["frames"][0]["t_sync"],
                        "end_time": track["frames"][-1]["t_sync"],
                        "alerts": [],
                    }
                    
                    # Detect Intrusions (Re-calculation)
                    for fr in track["frames"]:
                        # Center point
                        cx, cy = fr["x"], fr["y"]
                        # Check zones (ZoneManager API)
                        try:
                            zone_ids = self.zone_manager.check_point_all_zones(cx, cy, camera_id=video_id)
                        except Exception:
                            zone_ids = []

                        if zone_ids:
                            for zid in zone_ids:
                                z = self.zone_manager.zones.get(zid, {}) if hasattr(self.zone_manager, "zones") else {}
                                zone_name = z.get("name") or str(zid)
                                segment["alerts"].append({
                                    "time": fr.get("t_sync"),
                                    "zone": zone_name,
                                    "zone_id": str(zid),
                                })
                    
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
