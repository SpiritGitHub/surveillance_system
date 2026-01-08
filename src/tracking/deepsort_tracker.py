"""
Wrapper DeepSORT pour tracking des personnes
"""

from deep_sort_realtime.deepsort_tracker import DeepSort
import time


class DeepSortTracker:
    """Tracker DeepSORT avec sauvegarde des trajectoires"""
    
    def __init__(self, video_id):
        self.video_id = video_id
        
        # Initialiser DeepSORT
        self.tracker = DeepSort(
            max_age=30,           # Frames avant de supprimer un track
            n_init=3,             # Frames avant confirmation
            max_cosine_distance=0.2  # Seuil de similarité
        )
        
        self.trajectories = {}
        self.frame_count = 0
    
    def update(self, detections, frame):
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
                ([x1, y1, w, h], det["confidence"], "person")
            )
        
        # Mettre à jour le tracker
        tracks = self.tracker.update_tracks(ds_detections, frame=frame)
        
        # Timestamp
        timestamp = time.time()
        
        # Résultats à retourner
        results = []
        
        for track in tracks:
            # Ignorer les tracks non confirmés
            if not track.is_confirmed():
                continue
            
            track_id = track.track_id
            
            # Bbox format : left, top, right, bottom
            x1, y1, x2, y2 = map(int, track.to_ltrb())
            
            # Centre de la bbox
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            
            # Créer la trajectoire si elle n'existe pas
            if track_id not in self.trajectories:
                self.trajectories[track_id] = {
                    "track_id": track_id,
                    "video_id": self.video_id,
                    "first_frame": self.frame_count,
                    "last_frame": self.frame_count,
                    "frames": []
                }
            
            # Mettre à jour la trajectoire
            self.trajectories[track_id]["last_frame"] = self.frame_count
            self.trajectories[track_id]["frames"].append({
                "frame": self.frame_count,
                "x": cx,
                "y": cy,
                "t": timestamp,
                "bbox": [x1, y1, x2, y2]
            })
            
            # Ajouter aux résultats
            results.append({
                "track_id": track_id,
                "bbox": [x1, y1, x2, y2]
            })
        
        return results
    
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