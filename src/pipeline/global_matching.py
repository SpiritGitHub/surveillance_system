import json
import logging
from pathlib import Path
from tqdm import tqdm
import sys

# Add src to path
sys.path.append(str(Path(__file__).parents[2]))

from src.reid.matcher import ReIDMatcher

logger = logging.getLogger("GlobalMatching")

def run_global_matching(data_dir="data/trajectories", threshold=0.5, max_embeddings_per_track=5):
    """
    Load all trajectories, match them using ReID, and update JSONs with global_id.
    """
    print("\n" + "=" * 70)
    print("🌍 GLOBAL MATCHING (Re-ID)")
    print("=" * 70)
    
    traj_dir = Path(data_dir)
    json_files = list(traj_dir.glob("*.json"))
    
    if not json_files:
        print("❌ No trajectory files found.")
        return {
            "trajectory_files": 0,
            "tracks_with_embeddings": 0,
            "unique_identities": 0,
            "files_updated": 0,
            "threshold": threshold,
            "max_embeddings_per_track": max_embeddings_per_track,
        }

    matcher = ReIDMatcher(threshold=threshold)
    
    # 1. Load all tracks
    print(f"Loading {len(json_files)} trajectory files...")
    all_tracks = []  # items: {video_id, track_id, embeddings, timestamp, file_path, data, track_ref}
    
    for jf in json_files:
        try:
            with open(jf, "r") as f:
                data = json.load(f)
                
            video_id = data["video_id"]
            # Sort tracks by time? Or just process in order?
            # Ideally we process videos in chronological order if possible.
            # For now, we process file by file.
            
            for track in data["trajectories"]:
                class_name = track.get("class_name")
                # By default, we only do ReID global matching for persons.
                # Backward compatibility: if class_name is missing, assume person.
                if class_name is not None and class_name != "person":
                    continue
                if "embeddings" in track and track["embeddings"]:
                    embeddings = track["embeddings"]
                    # Prefer synchronized timestamp if present
                    first_frame = track["frames"][0].get("t_sync", track["frames"][0].get("t", 0.0))
                    
                    all_tracks.append({
                        "video_id": video_id,
                        "track_id": track["track_id"],
                        "embeddings": embeddings,
                        "timestamp": first_frame,
                        "file_path": jf,
                        "data": data,  # Keep ref to data to save it later
                        "track_ref": track,  # Direct ref to update without O(n) search
                    })
        except Exception as e:
            print(f"Error loading {jf}: {e}")

    # 2. Sort by timestamp to process chronologically
    all_tracks.sort(key=lambda x: x["timestamp"])
    
    print(f"Processing {len(all_tracks)} tracks with embeddings...")
    
    # 3. Match
    matches_count = 0
    new_ids_count = 0
    
    # Group by file to save later
    files_to_save = {}
    
    for track in tqdm(all_tracks, desc="Matching"):
        # Use mean embedding over first N samples to reduce noise
        import numpy as np
        embs = track["embeddings"][:max_embeddings_per_track]
        emb = np.mean(np.array(embs, dtype=np.float32), axis=0)
        
        global_id = matcher.match_track(emb, track["timestamp"])
        
        # Update track in memory (O(1))
        try:
            track_ref = track.get("track_ref")
            if isinstance(track_ref, dict):
                track_ref["global_id"] = global_id
        except Exception:
            # Fallback: leave track unchanged (will just reduce enrichment quality)
            pass
        
        files_to_save[track["file_path"]] = track["data"]

    # 4. Save updates
    print(f"\nSaving updates to {len(files_to_save)} files...")
    for path, data in files_to_save.items():
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            
    unique_identities = len(matcher.global_tracks)
    print(f"✓ Global matching complete. Total unique identities: {unique_identities}")

    return {
        "trajectory_files": len(json_files),
        "tracks_with_embeddings": len(all_tracks),
        "unique_identities": unique_identities,
        "files_updated": len(files_to_save),
        "threshold": threshold,
        "max_embeddings_per_track": max_embeddings_per_track,
    }

if __name__ == "__main__":
    run_global_matching()
