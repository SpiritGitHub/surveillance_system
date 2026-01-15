'''
process_video.py
Processeur de vidéos pour le système de surveillance.
'''
import cv2
import json
import logging
from pathlib import Path

from src.detection.yolo_detector import YOLODetector
from src.tracking.deepsort_tracker import DeepSortTracker
from src.metadata.metadata_manager import MetadataManager
from src.utils.orientation import ManualOrientationDetector
from src.zones.zone_manager import ZoneManager
from src.alerts.alert_manager import AlertManager
from src.reid.feature_extractor import FeatureExtractor


logger = logging.getLogger(__name__)


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
        show_video=False,
        event_output_file: str | None = None
    ):
        # Multi-class detection enabled by default (see src/detection/yolo_detector.py)
        self.detector = YOLODetector(model_path, conf_threshold)
        self.metadata_manager = MetadataManager()
        self.orientation_detector = ManualOrientationDetector()
        self.zone_manager = ZoneManager()
        self.alert_manager = AlertManager(output_file=event_output_file) if event_output_file else AlertManager()
        
        # Charger les offsets (durée + timestamp)
        self.offsets_duration = {}
        self.offsets_timestamp = {}
        try:
            with open("data/camera_offsets_durree.json", "r") as f:
                self.offsets_duration = json.load(f)
            print(f"[INFO] Chargé {len(self.offsets_duration)} offsets de durée")
        except Exception as e:
            print(f"[WARNING] Pas de fichier d'offsets trouvé: {e}")

        try:
            with open("data/camera_offsets_timestamp.json", "r") as f:
                self.offsets_timestamp = json.load(f)
            print(f"[INFO] Chargé {len(self.offsets_timestamp)} offsets timestamp")
        except Exception as e:
            print(f"[WARNING] Pas de fichier d'offsets timestamp trouvé: {e}")

        try:
            self.feature_extractor = FeatureExtractor()
            self.reid_enabled = True
        except Exception as e:
            print(f"[WARNING] ReID disabled: {e}")
            self.reid_enabled = False
            
        self.show_video = show_video

    def _reset_state_for_new_video(self) -> None:
        """Reset per-video state when reusing a single processor instance."""
        try:
            # Avoid intrusions leaking between videos when the processor is reused.
            self.alert_manager.active_intrusions.clear()
        except Exception:
            pass
    
    def process(self, video_path: str):
        """
        Traite une vidéo en 2 phases
        """
        # When reusing a processor across multiple videos, clear per-video state.
        self._reset_state_for_new_video()

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
        
        
        sync_offset = 0.0
        for key, val in self.offsets_timestamp.items():
            if video_id in key:
                sync_offset = float(val)
                break
        if sync_offset == 0.0:
            for key, val in self.offsets_duration.items():
                if video_id in key:
                    sync_offset = float(val)
                    break

        print(f"[INFO] Offset de synchronisation (base timeline): {sync_offset:.2f} sec")
        
        # ============================================================
        # PHASE 1: DÉTECTION ORIENTATION (pas de sauvegarde)
        # ============================================================
        print(f"\n[PHASE 1] Détection de l'orientation...")
        # Use detect_and_save which accepts a video path and persists choice
        rotation_k = self.orientation_detector.detect_and_save(str(video_path))
        print(f"[PHASE 1] ✓ Orientation finale: {rotation_k * 90}°")
        
        # ============================================================
        # PHASE 2: TRACKING COMPLET avec bonne orientation
        # ============================================================
        print(f"\n[PHASE 2] Tracking complet avec orientation {rotation_k * 90}°...")
        
        # Multi-class trackers (one DeepSORT instance per class)
        trackers = {}
        
        # Remettre au début
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        # Traiter avec la bonne orientation
        stats = self._process_with_rotation(
            cap, 
            trackers, 
            rotation_k, 
            video_id, 
            fps, 
            total_frames,
            sync_offset
        )
        
        cap.release()
        cv2.destroyAllWindows()
        
        # Sauvegarde
        print(f"\n[SAVE] Sauvegarde des trajectoires...")
        self._save_trajectories(video_id, trackers, traj_path, stats, rotation_k, sync_offset)
        
        print(f"\n[VIDEO] ✓ Traitement terminé")
        print('='*70)
        
        return stats
    
    def _process_with_rotation(self, cap, trackers, rotation_k, video_id, fps, total_frames, sync_offset):
        """
        PHASE 2: Traitement complet avec la bonne orientation
        C'est ICI qu'on sauvegarde les trajectoires
        """
        from tqdm import tqdm
        
        frame_id = 0
        total_detections = 0
        total_tracks = 0
        
        # Barre de progression
        pbar = tqdm(
            total=total_frames,
            desc="[PHASE 2] Tracking",
            unit="frame",
            ncols=100,
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        )
        
        frame_errors = 0
        logged_errors = 0

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

                    # Group detections by class
                    dets_by_class = {}
                    for det in detections:
                        cls_name = det.get("class_name", "object")
                        dets_by_class.setdefault(cls_name, []).append(det)

                    # Ensure trackers exist per class
                    for cls_name, dets in dets_by_class.items():
                        if cls_name not in trackers:
                            cls_id = dets[0].get("class_id") if dets else None
                            trackers[cls_name] = DeepSortTracker(video_id, class_name=cls_name, class_id=cls_id)
                    
                    # Tracking DeepSORT (use video-time timestamp, not wall clock)
                    video_time = frame_id / fps
                    tracks = []
                    for cls_name, dets in dets_by_class.items():
                        tracks.extend(trackers[cls_name].update(dets, frame, timestamp=video_time))
                    total_detections += len(detections)
                    total_tracks += len(tracks)

                    # Zone & Alert Check
                    current_time = frame_id / fps
                    current_time_sync = current_time + sync_offset
                    for trk in tracks:
                        tid = trk["track_id"]
                        x1, y1, x2, y2 = trk["bbox"]
                        class_name = trk.get("class_name")
                        
                        # Check zones
                        violations = self.zone_manager.check_bbox_all_zones([x1, y1, x2, y2], video_id) # Returns list of zone_ids
                        
                        # Update alerts
                        self.alert_manager.update(
                            tid,
                            violations,
                            current_time,
                            video_id,
                            frame_id,
                            class_name=class_name,
                            t_sync=current_time_sync,
                        )
                        
                        # Add alert info to track for visualization
                        trk["alerts"] = self.alert_manager.get_active_alerts(tid, current_time)

                        # ReID: Extract embedding periodically (e.g., every 30 frames ~ 1 sec)
                        if self.reid_enabled and class_name == "person" and frame_id % 30 == 0:
                            # Extract crop
                            h, w, _ = frame.shape
                            # Ensure bbox is within bounds
                            bx1, by1, bx2, by2 = [max(0, val) for val in [x1, y1, x2, y2]]
                            bx2, by2 = min(w, bx2), min(h, by2)
                            
                            if bx2 > bx1 and by2 > by1:
                                crop = frame[by1:by2, bx1:bx2]
                                embedding = self.feature_extractor.extract(crop)
                                # Persist embedding into tracker trajectories
                                try:
                                    trackers["person"].add_embedding(tid, embedding)
                                except Exception:
                                    # Fallback: attach to returned track dict so it's at least available during processing
                                    if "embeddings" not in trk:
                                        trk["embeddings"] = []
                                    trk["embeddings"].append(embedding.tolist())
                    
                    # Mettre à jour description avec nombre de tracks
                    if frame_id % 10 == 0:
                        pbar.set_postfix({'tracks': len(tracks), 'dets': len(detections)})
                    
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
                    # Continuer même si erreur sur une frame, mais ne pas masquer totalement.
                    frame_errors += 1
                    if logged_errors < 3:
                        logged_errors += 1
                        logger.exception(
                            "Erreur pendant le traitement d'une frame (video_id=%s, frame_id=%s)",
                            video_id,
                            frame_id,
                        )
                    continue
        finally:
            pbar.close()

        if frame_errors:
            logger.warning(
                "%d erreur(s) frame ignorée(s) pour video_id=%s (voir stacktraces des 3 premières)",
                frame_errors,
                video_id,
            )
        
        return {
            "frames_processed": frame_id,
            "total_detections": total_detections,
            "total_tracks": total_tracks,
            "unique_tracks": sum(len(t.get_trajectories()) for t in trackers.values()) if trackers else 0,
            "unique_by_class": {k: len(v.get_trajectories()) for k, v in trackers.items()},
            "unique_persons": len(trackers["person"].get_trajectories()) if "person" in trackers else 0,
            "rotation_applied": rotation_k * 90
        }
    
    def _show_frame(self, frame, tracks, frame_id, video_id):
        """Affiche la frame avec les tracks et les zones"""
        try:
            import numpy as np
            display = frame.copy()
            
            # Dessiner les zones
            zones = self.zone_manager.get_zones_for_camera(video_id)
            for zone in zones.values():
                if not zone.get("active", True):
                    continue
                
                pts = zone["_polygon_obj"].exterior.coords
                pts_int = np.array(pts, np.int32).reshape((-1, 1, 2))
                cv2.polylines(display, [pts_int], True, (0, 0, 255), 2)
                
                # Nom de la zone
                x, y = int(pts[0][0]), int(pts[0][1])
                cv2.putText(display, zone["name"], (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
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
                cls = trk.get("class_name", "")

                seed = abs(hash(str(tid)))
                color = (
                    (seed * 37) % 255,
                    (seed * 17) % 255,
                    (seed * 29) % 255
                )
                
                cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    display,
                    f"{cls} | {tid}",
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2
                )

                # Afficher alerte si présent
                if "alerts" in trk and trk["alerts"]:
                    alert_text = "ALERT!"
                    cv2.putText(
                        display,
                        alert_text,
                        (x1, y1 - 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2
                    )
            
            # Redimensionner si besoin
            h, w = display.shape[:2]
            if w > 1280:
                scale = 1280 / w
                display = cv2.resize(display, None, fx=scale, fy=scale)
            
            cv2.imshow(f"Tracking - {video_id}", display)
            
        except Exception:
            logger.exception("Erreur affichage frame (video_id=%s, frame_id=%s)", video_id, frame_id)
    
    def _save_trajectories(self, video_id, tracker, traj_path, stats, rotation_k, sync_offset=0.0):
        """Sauvegarde finale des trajectoires"""
        try:
            if isinstance(tracker, dict):
                trajectories = []
                for t in tracker.values():
                    trajectories.extend(list(t.get_trajectories().values()))
            else:
                trajectories = list(tracker.get_trajectories().values())
            
            # Appliquer l'offset de synchronisation aux timestamps
            for traj in trajectories:
                for frame_data in traj["frames"]:
                    # t est le timestamp relatif au début de la vidéo
                    # on ajoute l'offset pour avoir le temps synchronisé
                    frame_data["t_sync"] = frame_data["t"] + sync_offset
            
            data = {
                "video_id": video_id,
                "sync_offset": sync_offset,
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
            
        except Exception:
            logger.exception("Erreur sauvegarde trajectoires (video_id=%s, out=%s)", video_id, traj_path)
            print("[SAVE] ❌ Erreur lors de la sauvegarde (voir logs)")


def process_video(
    video_path: str,
    show_video: bool = False,
    event_output_file: str | None = None,
    processor: VideoProcessor | None = None,
):
    """
    Point d'entrée simple
    
    Args:
        video_path: Chemin de la vidéo
        show_video: Afficher la vidéo pendant le traitement
    """
    if processor is None:
        processor = VideoProcessor(show_video=show_video, event_output_file=event_output_file)
    else:
        # Keep caller expectations: allow overriding visualization per call.
        processor.show_video = bool(show_video)
    return processor.process(video_path)
