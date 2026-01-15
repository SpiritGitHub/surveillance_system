import logging

from scipy.spatial.distance import cosine

from src.utils.camera_network import CameraNetwork

logger = logging.getLogger("ReIDMatcher")

class ReIDMatcher:
    def __init__(
        self,
        threshold: float = 0.3,
        *,
        camera_network: CameraNetwork | None = None,
    ):
        """
        threshold: Cosine distance threshold (0.0 = identical, 2.0 = opposite)
        Lower is stricter. 0.3 is a reasonable starting point for ReID.
        """
        self.threshold = threshold
        # {global_id: {embeddings: [], last_seen: timestamp, last_camera: str|None}}
        self.global_tracks: dict[int, dict] = {}
        self.next_global_id = 1
        self.camera_network = camera_network

    def match_track(self, track_embedding, timestamp, camera_id: str | None = None):
        """
        Match a track embedding to existing global tracks.
        Returns: global_id (int)
        """
        best_match_id = None
        min_dist = float('inf')

        for gid, data in self.global_tracks.items():
            # Optional gating based on camera topology + time delta.
            if self.camera_network is not None:
                try:
                    last_seen = data.get("last_seen")
                    last_camera = data.get("last_camera")
                    dt_s = None
                    if last_seen is not None and timestamp is not None:
                        dt_s = float(timestamp) - float(last_seen)
                        # We process chronologically; still be tolerant if clocks are messy.
                        if dt_s < 0:
                            dt_s = abs(dt_s)
                    if not self.camera_network.allowed_transition(last_camera, camera_id, dt_s):
                        continue
                except Exception:
                    # If anything goes wrong, keep backward-compatible behavior.
                    pass

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
            self.global_tracks[best_match_id]["last_camera"] = camera_id
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
                "last_seen": timestamp,
                "last_camera": camera_id,
            }
            return new_id
