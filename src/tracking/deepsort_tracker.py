"""Wrapper DeepSORT pour tracking multi-classes."""

from deep_sort_realtime.deepsort_tracker import DeepSort
import time


class DeepSortTracker:
    """Tracker DeepSORT avec sauvegarde des trajectoires"""
    
    def __init__(self, video_id, class_name="person", class_id=None):
        self.video_id = video_id
        self.class_name = class_name
        self.class_id = class_id
        
        # Initialiser DeepSORT
        # NOTE: If you see too many fragmented IDs, increasing max_age and
        # relaxing max_cosine_distance can help keep identities stable.
        self.tracker = DeepSort(
            max_age=60,             # Frames before deleting a track
            n_init=3,               # Frames before confirmation
            max_cosine_distance=0.3 # Appearance distance threshold (higher = less strict)
        )
        
        self.trajectories = {}
        self.frame_count = 0
    
    def update(self, detections, frame, timestamp=None):
        """
        Met à jour le tracker avec les nouvelles détections
        
        Args:
            detections: Liste de détections YOLO [{bbox, confidence}]
            frame: Frame courante (pour DeepSORT)
        
        Returns:
            list: Liste des tracks [{track_id, bbox}]
        """
        self.frame_count += 1
        
        # Convertir détections YOLO au format DeepSORT
        ds_detections = []
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            w, h = x2 - x1, y2 - y1
            
            # Format DeepSORT : ([left, top, w, h], confidence, class)
            ds_detections.append(
                ([x1, y1, w, h], det["confidence"], self.class_name)
            )
        
        # Mettre à jour le tracker
        tracks = self.tracker.update_tracks(ds_detections, frame=frame)
        
        # Timestamp: prefer provided video-time timestamp (seconds since video start)
        if timestamp is None:
            timestamp = time.time()
        
        # Résultats à retourner
        results = []
        
        for track in tracks:
            # Ignorer les tracks non confirmés
            if not track.is_confirmed():
                continue
            
            track_id = track.track_id
            track_uid = f"{self.class_name}:{track_id}"
            
            # Bbox format : left, top, right, bottom
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            
            # Centre de la bbox
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            
            # Créer la trajectoire si elle n'existe pas
            if track_uid not in self.trajectories:
                self.trajectories[track_uid] = {
                    "track_id": track_uid,
                    "track_local_id": track_id,
                    "video_id": self.video_id,
                    "class_name": self.class_name,
                    "class_id": self.class_id,
                    "first_frame": self.frame_count,
                    "last_frame": self.frame_count,
                    "frames": [],
                    "embeddings": []
                }
            
            # Mettre à jour la trajectoire
            self.trajectories[track_uid]["last_frame"] = self.frame_count
            self.trajectories[track_uid]["frames"].append({
                "frame": self.frame_count,
                "x": cx,
                "y": cy,
                "t": timestamp,
                "bbox": [x1, y1, x2, y2]
            })
            
            # Ajouter aux résultats
            results.append({
                "track_id": track_uid,
                "track_local_id": track_id,
                "class_name": self.class_name,
                "class_id": self.class_id,
                "bbox": [x1, y1, x2, y2],
            })
        
        return results

    def add_embedding(self, track_id, embedding):
        """Append an embedding (list or array) to the stored trajectory for a track."""
        if track_id not in self.trajectories:
            # If trajectory doesn't exist yet, create a minimal entry
            self.trajectories[track_id] = {
                "track_id": track_id,
                "track_local_id": None,
                "video_id": self.video_id,
                "class_name": self.class_name,
                "class_id": self.class_id,
                "first_frame": self.frame_count,
                "last_frame": self.frame_count,
                "frames": [],
                "embeddings": []
            }

        if "embeddings" not in self.trajectories[track_id]:
            self.trajectories[track_id]["embeddings"] = []

        # Convert numpy arrays to list if necessary
        try:
            emb_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        except Exception:
            emb_list = embedding

        self.trajectories[track_id]["embeddings"].append(emb_list)
    
    def get_trajectories(self):
        """
        Retourne toutes les trajectoires enregistrées
        
        Returns:
            dict: Dictionnaire {track_id: trajectory}
        """
        # Ajouter statistiques sur chaque trajectoire
        for track_id, traj in self.trajectories.items():
            traj["total_frames"] = len(traj["frames"])
            traj["duration_frames"] = traj["last_frame"] - traj["first_frame"] + 1
        
        return self.trajectories
    
    def get_summary(self):
        """Retourne un résumé des trajectoires"""
        if not self.trajectories:
            return {
                "total_tracks": 0,
                "total_frames": self.frame_count,
                "avg_track_length": 0
            }
        
        total_points = sum(len(t["frames"]) for t in self.trajectories.values())
        
        return {
            "total_tracks": len(self.trajectories),
            "total_frames": self.frame_count,
            "avg_track_length": total_points / len(self.trajectories)
        }