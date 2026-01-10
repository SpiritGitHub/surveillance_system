import numpy as np
from scipy.spatial.distance import cosine
from collections import defaultdict
import logging

logger = logging.getLogger("ReIDMatcher")

class ReIDMatcher:
    def __init__(self, threshold=0.3):
        """
        threshold: Cosine distance threshold (0.0 = identical, 2.0 = opposite)
        Lower is stricter. 0.3 is a reasonable starting point for ReID.
        """
        self.threshold = threshold
        self.global_tracks = {} # {global_id: {embeddings: [], last_seen: timestamp}}
        self.next_global_id = 1

    def match_track(self, track_embedding, timestamp):
        """
        Match a track embedding to existing global tracks.
        Returns: global_id (int)
        """
        best_match_id = None
        min_dist = float('inf')

        for gid, data in self.global_tracks.items():
            # Compare with mean embedding of the global track
            # (Simple approach: average of stored embeddings)
            stored_embeddings = data["embeddings"]
            
            # Calculate distance to all stored embeddings and take the min or avg
            # Taking min distance to any previous appearance is often robust
            dists = [cosine(track_embedding, emb) for emb in stored_embeddings]
            dist = min(dists) if dists else 1.0
            
            if dist < min_dist:
                min_dist = dist
                best_match_id = gid

        if min_dist < self.threshold:
            # Match found
            self.global_tracks[best_match_id]["embeddings"].append(track_embedding)
            self.global_tracks[best_match_id]["last_seen"] = timestamp
            # Keep only recent embeddings to avoid drift? Or max N?
            if len(self.global_tracks[best_match_id]["embeddings"]) > 10:
                self.global_tracks[best_match_id]["embeddings"].pop(0)
            return best_match_id
        else:
            # New global ID
            new_id = self.next_global_id
            self.next_global_id += 1
            self.global_tracks[new_id] = {
                "embeddings": [track_embedding],
                "last_seen": timestamp
            }
            return new_id
