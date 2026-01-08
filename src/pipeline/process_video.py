'''
process_video.py
Processeur de vidéos pour le système de surveillance.
'''
import cv2
import json
from pathlib import Path

from src.detection.yolo_detector import YOLODetector
from src.tracking.deepsort_tracker import DeepSortTracker
from src.metadata.metadata_manager import MetadataManager
from src.utils.orientation import OrientationDetector


class VideoProcessor:
    """
    Processeur en 2 PHASES distinctes:
    PHASE 1: Test orientation (pas de sauvegarde)
    PHASE 2: Tracking complet avec la bonne orientation (sauvegarde)
    """
    
    def __init__(
        self,
        model_path="models/yolo/yolov8n.pt",
        conf_threshold=0.4,
        show_video=False
    ):
        self.detector = YOLODetector(model_path, conf_threshold)
        self.metadata_manager = MetadataManager()
        self.orientation_detector = OrientationDetector()
        self.show_video = show_video
    
    def process(self, video_path: str):
        """
        Traite une vidéo en 2 phases
        """
        video_path = Path(video_path)
        video_id = video_path.stem
        
        # Préparer dossiers
        Path("data/trajectories").mkdir(parents=True, exist_ok=True)
        traj_path = Path("data/trajectories") / f"{video_id}.json"
        
        print(f"\n{'='*70}")
        print(f"[VIDEO] {video_id}")
        print('='*70)
        
        # Ouvrir vidéo
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print("[ERROR] Impossible d'ouvrir la vidéo")
            return None
        
        # Infos vidéo
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        print(f"[INFO] {total_frames} frames @ {fps:.1f} fps ({width}x{height})")
        
        # ============================================================
        # PHASE 1: DÉTECTION ORIENTATION (pas de sauvegarde)
        # ============================================================
        print(f"\n[PHASE 1] Détection de l'orientation...")
        rotation_k = self.orientation_detector.detect(cap, self.detector.model)
        print(f"[PHASE 1] ✓ Orientation finale: {rotation_k * 90}°")
        
        # ============================================================
        # PHASE 2: TRACKING COMPLET avec bonne orientation
        # ============================================================
        print(f"\n[PHASE 2] Tracking complet avec orientation {rotation_k * 90}°...")
        
        # Créer le tracker MAINTENANT (pas avant)
        tracker = DeepSortTracker(video_id)
        
        # Remettre au début
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        # Traiter avec la bonne orientation
        stats = self._process_with_rotation(
            cap, 
            tracker, 
            rotation_k, 
            video_id, 
            fps, 
            total_frames
        )
        
        cap.release()
        cv2.destroyAllWindows()
        
        # Sauvegarde
        print(f"\n[SAVE] Sauvegarde des trajectoires...")
        self._save_trajectories(video_id, tracker, traj_path, stats, rotation_k)
        
        print(f"\n[VIDEO] ✓ Traitement terminé")
        print('='*70)
        
        return stats
    
    def _process_with_rotation(self, cap, tracker, rotation_k, video_id, fps, total_frames):
        """
        PHASE 2: Traitement complet avec la bonne orientation
        C'est ICI qu'on sauvegarde les trajectoires
        """
        from tqdm import tqdm
        
        frame_id = 0
        total_detections = 0
        
        # Barre de progression
        pbar = tqdm(
            total=total_frames,
            desc="[PHASE 2] Tracking",
            unit="frame",
            ncols=100,
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        )
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_id += 1
                pbar.update(1)
                
                try:
                    # Appliquer la rotation choisie
                    if rotation_k > 0:
                        frame = self.orientation_detector.rotate_frame(frame, rotation_k)
                    
                    # Détection YOLO
                    detections = self.detector.detect_frame(frame)
                    
                    # Tracking DeepSORT (sauvegarde dans le tracker)
                    tracks = tracker.update(detections, frame)
                    total_detections += len(tracks)
                    
                    # Mettre à jour description avec nombre de tracks
                    if frame_id % 10 == 0:
                        pbar.set_postfix({'tracks': len(tracks), 'total_det': total_detections})
                    
                    # Visualisation optionnelle
                    if self.show_video:
                        self._show_frame(frame, tracks, frame_id, video_id)
                        
                        # Quitter si 'q'
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            pbar.close()
                            print("\n[PHASE 2] Arrêt demandé")
                            break
                        
                except KeyboardInterrupt:
                    pbar.close()
                    print("\n[PHASE 2] Interruption")
                    break
                except Exception as e:
                    # Continuer même si erreur sur une frame
                    continue
        finally:
            pbar.close()
        
        return {
            "frames_processed": frame_id,
            "total_detections": total_detections,
            "unique_persons": len(tracker.get_trajectories()),
            "rotation_applied": rotation_k * 90
        }
    
    def _show_frame(self, frame, tracks, frame_id, video_id):
        """Affiche la frame avec les tracks"""
        try:
            display = frame.copy()
            
            # Info en haut
            cv2.putText(
                display,
                f"Frame: {frame_id} | Tracks: {len(tracks)}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )
            
            # Dessiner tracks
            for trk in tracks:
                x1, y1, x2, y2 = trk["bbox"]
                tid = trk["track_id"]
                
                color = (
                    (tid * 37) % 255,
                    (tid * 17) % 255,
                    (tid * 29) % 255
                )
                
                cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    display,
                    f"ID {tid}",
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2
                )
            
            # Redimensionner si besoin
            h, w = display.shape[:2]
            if w > 1280:
                scale = 1280 / w
                display = cv2.resize(display, None, fx=scale, fy=scale)
            
            cv2.imshow(f"Tracking - {video_id}", display)
            
        except Exception as e:
            pass
    
    def _save_trajectories(self, video_id, tracker, traj_path, stats, rotation_k):
        """Sauvegarde finale des trajectoires"""
        try:
            trajectories = list(tracker.get_trajectories().values())
            
            data = {
                "video_id": video_id,
                "rotation_applied": rotation_k * 90,
                "stats": stats,
                "trajectories": trajectories
            }
            
            with open(traj_path, "w") as f:
                json.dump(data, f, indent=2)
            
            file_size_kb = traj_path.stat().st_size / 1024
            total_positions = sum(len(t["frames"]) for t in trajectories)
            
            print(f"[SAVE] ✓ {len(trajectories)} trajectoire(s)")
            print(f"[SAVE] ✓ {total_positions} positions")
            print(f"[SAVE] ✓ Taille: {file_size_kb:.1f} KB")
            print(f"[SAVE] ✓ Fichier: {traj_path}")
            
        except Exception as e:
            print(f"[SAVE] ❌ Erreur: {e}")


def process_video(video_path: str, show_video=False):
    """
    Point d'entrée simple
    
    Args:
        video_path: Chemin de la vidéo
        show_video: Afficher la vidéo pendant le traitement
    """
    processor = VideoProcessor(show_video=show_video)
    return processor.process(video_path)
