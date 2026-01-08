# src/utils/frame_saver.py
"""
Sauvegarde des frames annotées
"""

import cv2
import json
from pathlib import Path


class FrameSaver:
    """Gère la sauvegarde des frames avec annotations"""
    
    def __init__(self, output_dir="data/frames", quality=85):
        self.output_dir = Path(output_dir)
        self.quality = quality
    
    def prepare_directory(self, video_id: str):
        """Crée le dossier pour une vidéo"""
        frames_dir = self.output_dir / video_id
        frames_dir.mkdir(parents=True, exist_ok=True)
        return frames_dir
    
    def save(self, frame, video_id, frame_id, detections, timestamp):
        """
        Sauvegarde une frame avec annotations
        
        Args:
            frame: Image à sauvegarder
            video_id: ID de la vidéo
            frame_id: Numéro de frame
            detections: Liste des détections (avec track_id et bbox)
            timestamp: Timestamp en secondes
        
        Returns:
            str: Chemin de la frame sauvegardée
        """
        frames_dir = self.output_dir / video_id
        
        # Annoter la frame
        annotated = self._annotate_frame(frame.copy(), frame_id, timestamp, detections)
        
        # Sauvegarder image
        frame_path = frames_dir / f"frame_{frame_id:06d}.jpg"
        cv2.imwrite(
            str(frame_path), 
            annotated, 
            [cv2.IMWRITE_JPEG_QUALITY, self.quality]
        )
        
        # Sauvegarder métadonnées JSON
        self._save_frame_metadata(frames_dir, frame_id, timestamp, detections)
        
        return str(frame_path)
    
    def _annotate_frame(self, frame, frame_id, timestamp, detections):
        """Annote une frame avec bboxes et infos"""
        # Timestamp en haut
        cv2.putText(
            frame,
            f"Frame: {frame_id} | Time: {timestamp:.2f}s",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )
        
        # Bounding boxes
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            tid = det["track_id"]
            
            # Couleur unique par ID
            color = (
                (tid * 37) % 255,
                (tid * 17) % 255,
                (tid * 29) % 255
            )
            
            # Rectangle
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Label ID
            cv2.putText(
                frame,
                f"ID {tid}",
                (x1, y1 - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )
        
        return frame
    
    def _save_frame_metadata(self, frames_dir, frame_id, timestamp, detections):
        """Sauvegarde les métadonnées JSON d'une frame"""
        frame_meta = {
            "frame_id": frame_id,
            "timestamp": timestamp,
            "detections_count": len(detections),
            "tracks": [
                {
                    "track_id": det["track_id"],
                    "bbox": det["bbox"]
                }
                for det in detections
            ]
        }
        
        meta_path = frames_dir / f"frame_{frame_id:06d}.json"
        with open(meta_path, 'w') as f:
            json.dump(frame_meta, f, indent=2)