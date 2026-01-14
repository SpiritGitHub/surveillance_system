"""
Outil de synchronisation manuelle des vidéos
Permet de définir le décalage (offset) de chaque caméra pour les synchroniser
Version améliorée avec lecture simultanée des vidéos
"""

import cv2
import numpy as np
from pathlib import Path
import json
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.orientation import ManualOrientationDetector


class DualVideoPlayer:
    """Lecteur pour afficher deux vidéos en parallèle"""
    
    def __init__(self, ref_path, target_path, orientation_detector):
        self.ref_path = ref_path
        self.target_path = target_path
        self.orientation_detector = orientation_detector
        
        # Ouvrir les vidéos
        self.ref_cap = cv2.VideoCapture(str(ref_path))
        self.target_cap = cv2.VideoCapture(str(target_path))
        
        if not self.ref_cap.isOpened() or not self.target_cap.isOpened():
            raise Exception("Impossible d'ouvrir les vidéos")
        
        # Propriétés des vidéos
        self.ref_fps = self.ref_cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.target_fps = self.target_cap.get(cv2.CAP_PROP_FPS) or 30.0
        
        self.ref_total_frames = int(self.ref_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.target_total_frames = int(self.target_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # État de lecture
        self.ref_time = 0.0
        self.target_time = 0.0
        self.is_playing = False
        self.playback_speed = 1.0
        
        # IDs pour rotation
        self.ref_id = Path(ref_path).stem.replace("CAMERA_", "")
        self.target_id = Path(target_path).stem.replace("CAMERA_", "")
        
    def set_time(self, ref_time, target_time):
        """Définir le temps de lecture pour chaque vidéo"""
        self.ref_time = max(0, ref_time)
        self.target_time = max(0, target_time)
        
        ref_frame = int(self.ref_time * self.ref_fps)
        target_frame = int(self.target_time * self.target_fps)
        
        self.ref_cap.set(cv2.CAP_PROP_POS_FRAMES, ref_frame)
        self.target_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    
    def read_frames(self):
        """Lire les frames actuelles"""
        ret_ref, frame_ref = self.ref_cap.read()
        ret_target, frame_target = self.target_cap.read()
        
        if not ret_ref or not ret_target:
            return None, None
        
        # Appliquer les rotations
        rotation_ref = self.orientation_detector.get_orientation(self.ref_id)
        if rotation_ref > 0:
            frame_ref = self.orientation_detector.rotate_frame(frame_ref, rotation_ref)
        
        rotation_target = self.orientation_detector.get_orientation(self.target_id)
        if rotation_target > 0:
            frame_target = self.orientation_detector.rotate_frame(frame_target, rotation_target)
        
        # Redimensionner pour affichage côte à côte
        frame_ref = self.resize_frame(frame_ref, 640)
        frame_target = self.resize_frame(frame_target, 640)
        
        return frame_ref, frame_target
    
    def resize_frame(self, frame, target_width):
        """Redimensionner une frame"""
        h, w = frame.shape[:2]
        if w > target_width:
            scale = target_width / w
            new_w = target_width
            new_h = int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h))
        return frame
    
    def create_display(self, frame_ref, frame_target):
        """Créer l'affichage avec les deux vidéos côte à côte"""
        # Assurer la même hauteur
        h_ref, w_ref = frame_ref.shape[:2]
        h_target, w_target = frame_target.shape[:2]
        
        max_height = max(h_ref, h_target)
        
        # Padding si nécessaire
        if h_ref < max_height:
            padding = max_height - h_ref
            frame_ref = cv2.copyMakeBorder(frame_ref, 0, padding, 0, 0, 
                                          cv2.BORDER_CONSTANT, value=(0, 0, 0))
        if h_target < max_height:
            padding = max_height - h_target
            frame_target = cv2.copyMakeBorder(frame_target, 0, padding, 0, 0,
                                             cv2.BORDER_CONSTANT, value=(0, 0, 0))
        
        # Combiner côte à côte
        display = np.hstack([frame_ref, frame_target])
        
        # Ajouter les informations
        self.add_overlay(display, frame_ref.shape[1])
        
        return display
    
    def add_overlay(self, display, split_x):
        """Ajouter les informations sur l'affichage"""
        # Barre supérieure
        cv2.rectangle(display, (0, 0), (display.shape[1], 80), (0, 0, 0), -1)
        
        # Informations vidéo de référence
        ref_time_str = f"{int(self.ref_time//60):02d}:{int(self.ref_time%60):02d}.{int((self.ref_time%1)*10)}"
        cv2.putText(display, f"REFERENCE: {self.ref_id}", (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(display, f"Temps: {ref_time_str}", (10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Informations vidéo cible
        target_time_str = f"{int(self.target_time//60):02d}:{int(self.target_time%60):02d}.{int((self.target_time%1)*10)}"
        cv2.putText(display, f"CIBLE: {self.target_id}", (split_x + 10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(display, f"Temps: {target_time_str}", (split_x + 10, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Décalage actuel
        offset = self.ref_time - self.target_time
        offset_str = f"Decalage: {offset:+.2f}s"
        cv2.putText(display, offset_str, (10, 75),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # État de lecture
        status = "LECTURE" if self.is_playing else "PAUSE"
        status_color = (0, 255, 0) if self.is_playing else (0, 165, 255)
        cv2.putText(display, status, (split_x + 10, 75),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
        
        # Ligne de séparation
        cv2.line(display, (split_x, 0), (split_x, display.shape[0]), (255, 255, 255), 2)
    
    def release(self):
        """Libérer les ressources"""
        self.ref_cap.release()
        self.target_cap.release()


class VideoSyncTool:
    """Outil pour synchroniser manuellement les vidéos"""
    
    def __init__(self):
        self.orientation_detector = ManualOrientationDetector()
        self.offsets = {}
        self.offsets_file = Path("data/camera_offsets.json")
        self.load_offsets()
    
    def load_offsets(self):
        """Charge les offsets existants"""
        if self.offsets_file.exists():
            with open(self.offsets_file, 'r', encoding='utf-8') as f:
                self.offsets = json.load(f)
            print(f"OK: {len(self.offsets)} offset(s) chargé(s)")
    
    def save_offsets(self):
        """Sauvegarde les offsets"""
        self.offsets_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.offsets_file, 'w', encoding='utf-8') as f:
            json.dump(self.offsets, f, indent=2, ensure_ascii=False)
        print(f"\nOffsets sauvegardés: {self.offsets_file}")
    
    def configure_offset(self, ref_video_path, ref_camera_id, target_video_path, target_camera_id):
        """Configure l'offset pour une caméra en comparaison avec la référence"""
        print(f"\n{'='*70}")
        print(f"Synchronisation: {target_camera_id} avec {ref_camera_id} (référence)")
        print('='*70)
        
        # Offset actuel
        current_offset = self.offsets.get(target_camera_id, 0)
        print(f"\nOffset actuel: {current_offset}s")
        
        print("\nInstructions:")
        print("   Contrôles de lecture:")
        print("      ESPACE = Lecture/Pause")
        print("      Flèche gauche/droite = -1s / +1s sur les DEUX vidéos")
        print("      A D = -0.1s / +0.1s sur la vidéo CIBLE uniquement")
        print("      Q W = -5s / +5s sur les DEUX vidéos")
        print("      Z X = -10s / +10s sur les DEUX vidéos")
        print("      R = Retour au début")
        print("      S = Vitesse (0.25x / 0.5x / 1x)")
        print("\n   Synchronisation:")
        print("      Trouvez un événement commun et ajustez jusqu'à ce qu'il")
        print("      apparaisse au MÊME MOMENT sur les deux vidéos")
        print("\n      ENTER = Confirmer et calculer l'offset")
        print("      ESC = Annuler")
        
        try:
            # Créer le lecteur double
            player = DualVideoPlayer(ref_video_path, target_video_path, self.orientation_detector)
            
            # Position initiale
            start_ref = 10.0
            start_target = start_ref - current_offset
            player.set_time(start_ref, start_target)
            
            window_name = "Synchronisation - Appuyez sur ESPACE pour lire"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 1400, 700)
            
            last_frame_time = time.time()
            speed_modes = [0.25, 0.5, 1.0]
            speed_index = 2
            
            while True:
                current_time = time.time()
                
                # Lire les frames
                frame_ref, frame_target = player.read_frames()
                
                if frame_ref is None or frame_target is None:
                    # Fin de vidéo, revenir au début
                    player.set_time(player.ref_time, player.target_time)
                    player.is_playing = False
                    continue
                
                # Créer l'affichage
                display = player.create_display(frame_ref, frame_target)
                
                # Afficher les contrôles
                self.add_help_overlay(display, speed_modes[speed_index])
                
                cv2.imshow(window_name, display)
                
                # Gestion du timing pour la lecture
                wait_time = 1 if not player.is_playing else max(1, int(1000 / (player.ref_fps * speed_modes[speed_index])))
                key = cv2.waitKey(wait_time) & 0xFF
                
                # Avancer le temps si en lecture
                if player.is_playing:
                    frame_duration = 1.0 / player.ref_fps
                    player.ref_time += frame_duration * speed_modes[speed_index]
                    player.target_time += frame_duration * speed_modes[speed_index]
                    player.set_time(player.ref_time, player.target_time)
                
                # Gestion des touches
                if key == 27:  # ESC
                    player.release()
                    cv2.destroyAllWindows()
                    return None
                    
                elif key == 13:  # ENTER
                    break
                    
                elif key == 32:  # ESPACE - Lecture/Pause
                    player.is_playing = not player.is_playing
                    
                elif key == ord('s') or key == ord('S'):  # Changer vitesse
                    speed_index = (speed_index + 1) % len(speed_modes)
                    print(f"   Vitesse: {speed_modes[speed_index]}x")
                    
                elif key == ord('r') or key == ord('R'):  # Reset
                    player.set_time(10.0, 10.0 - current_offset)
                    player.is_playing = False
                    
                elif key == 81 or key == 2:  # Flèche gauche - Reculer ensemble
                    player.is_playing = False
                    player.ref_time -= 1.0
                    player.target_time -= 1.0
                    player.set_time(player.ref_time, player.target_time)
                    
                elif key == 83 or key == 3:  # Flèche droite - Avancer ensemble
                    player.is_playing = False
                    player.ref_time += 1.0
                    player.target_time += 1.0
                    player.set_time(player.ref_time, player.target_time)
                    
                elif key == ord('a') or key == ord('A'):  # Reculer cible
                    player.is_playing = False
                    player.target_time -= 0.1
                    player.set_time(player.ref_time, player.target_time)
                    
                elif key == ord('d') or key == ord('D'):  # Avancer cible
                    player.is_playing = False
                    player.target_time += 0.1
                    player.set_time(player.ref_time, player.target_time)
                    
                elif key == ord('q') or key == ord('Q'):  # Reculer 5s ensemble
                    player.is_playing = False
                    player.ref_time -= 5.0
                    player.target_time -= 5.0
                    player.set_time(player.ref_time, player.target_time)
                    
                elif key == ord('w') or key == ord('W'):  # Avancer 5s ensemble
                    player.is_playing = False
                    player.ref_time += 5.0
                    player.target_time += 5.0
                    player.set_time(player.ref_time, player.target_time)
                    
                elif key == ord('z') or key == ord('Z'):  # Reculer 10s ensemble
                    player.is_playing = False
                    player.ref_time -= 10.0
                    player.target_time -= 10.0
                    player.set_time(player.ref_time, player.target_time)
                    
                elif key == ord('x') or key == ord('X'):  # Avancer 10s ensemble
                    player.is_playing = False
                    player.ref_time += 10.0
                    player.target_time += 10.0
                    player.set_time(player.ref_time, player.target_time)
            
            # Calculer l'offset final
            offset = player.ref_time - player.target_time
            
            player.release()
            cv2.destroyAllWindows()
            
            print(f"\n✓ Offset calculé: {offset:.2f}s")
            if offset > 0:
                print(f"   La vidéo cible est EN RETARD de {offset:.2f}s")
            elif offset < 0:
                print(f"   La vidéo cible est EN AVANCE de {-offset:.2f}s")
            else:
                print("   Les vidéos sont synchronisées")
            
            confirm = input("\nSauvegarder cet offset ? (o/n) [o]: ").strip().lower()
            if confirm != 'n':
                return offset
            
            return None
            
        except Exception as e:
            print(f"ERREUR: {e}")
            return None
    
    def add_help_overlay(self, display, speed):
        """Ajouter l'aide en bas de l'écran"""
        h = display.shape[0]
        cv2.rectangle(display, (0, h-60), (display.shape[1], h), (0, 0, 0), -1)
        
        help_text = f"ESPACE: Play/Pause | Fleches: ±1s | AD: ±0.1s cible | QW: ±5s | ZX: ±10s | S: Vitesse({speed}x) | R: Reset | ENTER: Valider | ESC: Annuler"
        cv2.putText(display, help_text, (10, h-35),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


def main():
    """Point d'entrée"""
    print("\n" + "=" * 70)
    print("OUTIL DE SYNCHRONISATION VIDÉO")
    print("=" * 70)
    print("\nCet outil permet de synchroniser les caméras en les visualisant")
    print("simultanément et en ajustant leur décalage temporel.")
    print("=" * 70)
    
    # Charger les vidéos
    video_dir = Path("data/videos")
    videos = sorted(list(video_dir.glob("*.mp4")))
    
    if not videos:
        print("\nERREUR: aucune vidéo trouvée dans data/videos/")
        return
    
    print(f"\nOK: {len(videos)} vidéo(s) trouvée(s)")
    
    # Afficher les vidéos
    print("\nCaméras disponibles:")
    for i, video in enumerate(videos, 1):
        camera_id = video.stem.replace("CAMERA_", "")
        print(f"   [{i}] {camera_id}")
    
    # Demander la caméra de référence
    print("\nQuelle caméra voulez-vous utiliser comme RÉFÉRENCE ?")
    print("   (Son offset sera 0, les autres seront calculés par rapport à elle)")
    
    ref_choice = input("\nNuméro de la caméra de référence [1]: ").strip()
    ref_idx = int(ref_choice) - 1 if ref_choice else 0
    
    if ref_idx < 0 or ref_idx >= len(videos):
        print("ERREUR: choix invalide")
        return
    
    ref_video = videos[ref_idx]
    ref_camera_id = ref_video.stem.replace("CAMERA_", "")
    
    print(f"\nOK: caméra de référence: {ref_camera_id}")
    
    # Créer l'outil
    tool = VideoSyncTool()
    
    # Définir l'offset de référence à 0
    tool.offsets[ref_camera_id] = 0
    print(f"   Offset: 0s")
    
    # Configurer les autres caméras
    print("\n" + "=" * 70)
    print("Configuration des autres caméras")
    print("=" * 70)
    
    for i, video in enumerate(videos, 1):
        camera_id = video.stem.replace("CAMERA_", "")
        
        if camera_id == ref_camera_id:
            continue
        
        print(f"\n[{i-1}/{len(videos)-1}] Configuration de {camera_id}")
        
        choice = input("   Configurer cette caméra ? (o/n/q pour quitter) [o]: ").strip().lower()
        
        if choice == 'q':
            print("\nArrêt demandé")
            break
        
        if choice == 'n':
            print("   Caméra ignorée")
            continue
        
        offset = tool.configure_offset(ref_video, ref_camera_id, video, camera_id)
        
        if offset is not None:
            tool.offsets[camera_id] = offset
            print(f"   OK: offset enregistré: {offset:.2f}s")
    
    # Sauvegarder
    if tool.offsets:
        tool.save_offsets()
        
        print("\n" + "=" * 70)
        print("RÉSUMÉ DES OFFSETS")
        print("=" * 70)
        
        for camera_id, offset in sorted(tool.offsets.items()):
            status = "RÉFÉRENCE" if offset == 0 else f"{offset:+.2f}s"
            print(f"   {camera_id:40s} {status}")
        
        print("\nOK: configuration terminée")
        print(f"Fichier: {tool.offsets_file}")
        print("\nCes offsets seront maintenant utilisés par le visualiseur multi-caméras")
    else:
        print("\nAVERTISSEMENT: aucun offset configuré")


if __name__ == "__main__":
    main()