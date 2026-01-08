"""
Gestion centralisée de toutes les métadonnées
"""

import json
from pathlib import Path
from datetime import datetime
from pymediainfo import MediaInfo
import cv2


# ==========================================================
# CONFIG CAMERAS ( le gps est faux car non attache a la video )
# ==========================================================
CAMERA_CONFIG = {
    "CAMERA_DEBUT_COULOIR_DROIT": {
        "location": "Couloir principal - Entrée droite",
        "gps": {"lat": 6.1256, "lon": 1.2226},
        "zone_type": "corridor",
        "floor": 0,
        "camera_id": "CAM_001"
    },
    "CAMERA_DEVANTURE_PORTE_ENTREE": {
        "location": "Devanture - Porte d'entrée",
        "gps": {"lat": 6.1257, "lon": 1.2227},
        "zone_type": "entrance",
        "floor": 0,
        "camera_id": "CAM_002"
    },
    "CAMERA_DEVANTURE_SOUS_ARBRE": {
        "location": "Devanture - Sous l'arbre",
        "gps": {"lat": 6.1258, "lon": 1.2228},
        "zone_type": "outdoor",
        "floor": 0,
        "camera_id": "CAM_003"
    },
    "CAMERA_ESCALIER_DEBUT_COULOIR_GAUCHE": {
        "location": "Escalier - Début couloir gauche",
        "gps": {"lat": 6.1259, "lon": 1.2229},
        "zone_type": "stairway",
        "floor": 0,
        "camera_id": "CAM_004"
    },
    "CAMERA_FIN_COULOIR_DROIT": {
        "location": "Fin couloir droit",
        "gps": {"lat": 6.1260, "lon": 1.2230},
        "zone_type": "corridor",
        "floor": 0,
        "camera_id": "CAM_005"
    },
    "CAMERA_FIN_COULOIR_GAUCHE_ETAGE1": {
        "location": "Fin couloir gauche - Étage 1",
        "gps": {"lat": 6.1261, "lon": 1.2231},
        "zone_type": "corridor",
        "floor": 1,
        "camera_id": "CAM_006"
    },
    "CAMERA_FIN_COULOIR_GAUCHE_REZ_PARTIE_1": {
        "location": "Fin couloir gauche RDC - Partie 1",
        "gps": {"lat": 6.1262, "lon": 1.2232},
        "zone_type": "corridor",
        "floor": 0,
        "camera_id": "CAM_007"
    },
    "CAMERA_FIN_COULOIR_GAUCHE_REZ_PARTIE_2": {
        "location": "Fin couloir gauche RDC - Partie 2",
        "gps": {"lat": 6.1263, "lon": 1.2233},
        "zone_type": "corridor",
        "floor": 0,
        "camera_id": "CAM_008"
    },
    "CAMERA_HALL_PORTE_DROITE": {
        "location": "Hall - Porte droite",
        "gps": {"lat": 6.1264, "lon": 1.2234},
        "zone_type": "hall",
        "floor": 0,
        "camera_id": "CAM_009"
    },
    "CAMERA_HALL_PORTE_ENTREE": {
        "location": "Hall - Porte d'entrée",
        "gps": {"lat": 6.1265, "lon": 1.2235},
        "zone_type": "hall",
        "floor": 0,
        "camera_id": "CAM_010"
    },
    "CAMERA_HALL_PORTE_GAUCHE": {
        "location": "Hall - Porte gauche",
        "gps": {"lat": 6.1266, "lon": 1.2236},
        "zone_type": "hall",
        "floor": 0,
        "camera_id": "CAM_011"
    }
}


class MetadataManager:
    """Gestion centralisée des métadonnées vidéo"""
    
    def __init__(self):
        self.drive_metadata_file = Path("data/videos/videos_metadata.json")
    
    def load_drive_metadata(self, video_path: Path):
        """Charge les métadonnées Google Drive"""
        if not self.drive_metadata_file.exists():
            return {}
        
        with open(self.drive_metadata_file, 'r') as f:
            all_metadata = json.load(f)
        
        return all_metadata.get(video_path.name, {})
    
    def extract_video_exif(self, video_path: Path):
        """Extrait les métadonnées EXIF/MediaInfo"""
        exif_data = {}
        
        try:
            media_info = MediaInfo.parse(str(video_path))
            
            for track in media_info.tracks:
                if track.track_type == "General":
                    if hasattr(track, 'recorded_date') and track.recorded_date:
                        exif_data["recorded_date"] = track.recorded_date
                    if hasattr(track, 'tagged_date') and track.tagged_date:
                        exif_data["tagged_date"] = track.tagged_date
                    if hasattr(track, 'file_last_modification_date') and track.file_last_modification_date:
                        exif_data["file_modified"] = track.file_last_modification_date
                
                if track.track_type == "Video":
                    if hasattr(track, 'gps_latitude'):
                        exif_data["gps_latitude"] = track.gps_latitude
                    if hasattr(track, 'gps_longitude'):
                        exif_data["gps_longitude"] = track.gps_longitude
        
        except Exception as e:
            print(f"[EXIF] ⚠️ Erreur extraction : {e}")
        
        return exif_data
    
    def get_camera_config(self, video_id: str):
        """Récupère la config d'une caméra"""
        return CAMERA_CONFIG.get(video_id, {})
    
    def extract_all(self, video_path: Path):
        """
        Extrait TOUTES les métadonnées d'une vidéo
        
        Returns:
            dict: Métadonnées complètes
        """
        cap = cv2.VideoCapture(str(video_path))
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        metadata = {
            "video_id": video_path.stem,
            "filename": video_path.name,
            "fps": fps,
            "total_frames": total_frames,
            "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "duration_sec": int(total_frames / fps) if fps > 0 else 0,
            "file_size_mb": round(video_path.stat().st_size / (1024 * 1024), 2),
            "processing_date": datetime.now().isoformat()
        }
        
        cap.release()
        
        # Ajouter métadonnées Drive
        drive_meta = self.load_drive_metadata(video_path)
        if drive_meta:
            metadata["drive"] = {
                "file_id": drive_meta.get("file_id"),
                "created_time": drive_meta.get("created_time"),
                "modified_time": drive_meta.get("modified_time"),
                "downloaded_at": drive_meta.get("downloaded_at")
            }
        
        # Ajouter EXIF
        exif_data = self.extract_video_exif(video_path)
        if exif_data:
            metadata["exif"] = exif_data
        
        # Ajouter config caméra
        camera_config = self.get_camera_config(video_path.stem)
        if camera_config:
            metadata["camera"] = camera_config
        
        return metadata
    
    def save_metadata(self, video_id: str, metadata: dict, output_dir="data/metadata"):
        """Sauvegarde les métadonnées"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        meta_path = Path(output_dir) / f"{video_id}.json"
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return meta_path
    
    def print_summary(self, metadata: dict):
        """Affiche un résumé des métadonnées"""
        print(f"[METADATA] 📊 Résumé :")
        print(f"[METADATA]   → Caméra : {metadata.get('camera', {}).get('location', 'Inconnue')}")
        print(f"[METADATA]   → Durée : {metadata['duration_sec']}s ({metadata['total_frames']} frames)")
        print(f"[METADATA]   → Résolution : {metadata['width']}x{metadata['height']}")
        print(f"[METADATA]   → Taille : {metadata['file_size_mb']} MB")
        
        if metadata.get('drive'):
            print(f"[METADATA]   → Créé le : {metadata['drive'].get('created_time', 'N/A')}")
        
        if metadata.get('exif'):
            print(f"[METADATA]   → EXIF : {list(metadata['exif'].keys())}")