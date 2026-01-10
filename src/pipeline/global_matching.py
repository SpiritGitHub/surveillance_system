import json
import logging
from pathlib import Path
from tqdm import tqdm
import sys

# Add src to path
sys.path.append(str(Path(__file__).parents[2]))

from src.reid.matcher import ReIDMatcher

logger = logging.getLogger("GlobalMatching")

def run_global_matching(data_dir="data/trajectories", threshold=0.3):
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
        return

    matcher = ReIDMatcher(threshold=threshold)
    
    # 1. Load all tracks
    print(f"Loading {len(json_files)} trajectory files...")
    all_tracks = [] # (video_id, track_id, embeddings, timestamp)
    
    for jf in json_files:
        try:
            with open(jf, "r") as f:
                data = json.load(f)
                
            video_id = data["video_id"]
            # Sort tracks by time? Or just process in order?
            # Ideally we process videos in chronological order if possible.
            # For now, we process file by file.
            
            for track in data["trajectories"]:
                if "embeddings" in track and track["embeddings"]:
                    # Use the first embedding for matching (or average?)
                    # Let's use the first one for simplicity, or iterate
                    # track["embeddings"] is a list of lists
                    embeddings = track["embeddings"]
                    # timestamp of first appearance
                    first_frame = track["frames"][0]["t"]
                    
                    all_tracks.append({
                        "video_id": video_id,
                        "track_id": track["track_id"],
                        "embeddings": embeddings,
                        "timestamp": first_frame,
                        "file_path": jf,
                        "data": data # Keep ref to data to update it
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
        # Use average embedding for better robustness?
        # Or just match the first one?
        # Let's try matching the first embedding
        import numpy as np
        emb = np.array(track["embeddings"][0])
        
        global_id = matcher.match_track(emb, track["timestamp"])
        
        # Update track in memory
        # We need to find the track in the original data structure
        # We have a ref to 'data' in the list item
        
        # Find the specific track object in the data['trajectories'] list
        # This is a bit inefficient but safe
        for t in track["data"]["trajectories"]:
            if t["track_id"] == track["track_id"]:
                t["global_id"] = global_id
                break
        
        files_to_save[track["file_path"]] = track["data"]

    # 4. Save updates
    print(f"\nSaving updates to {len(files_to_save)} files...")
    for path, data in files_to_save.items():
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            
    print(f"✓ Global matching complete. Total unique identities: {len(matcher.global_tracks)}")

if __name__ == "__main__":
    run_global_matching()
