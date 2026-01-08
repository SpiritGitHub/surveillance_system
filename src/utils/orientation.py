"""
Détection manuelle d'orientation
Affiche 4 versions d'une frame, l'utilisateur choisit la bonne
"""

import cv2
import json
from pathlib import Path
import numpy as np


class ManualOrientationDetector:
    """Détecteur d'orientation manuel avec choix utilisateur"""
    
    def __init__(self, config_file="data/video_orientations.json"):
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.orientations = self.load_orientations()
    
    def load_orientations(self):
        """Charge les orientations sauvegardées"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {}
    
    def save_orientations(self):
        """Sauvegarde les orientations"""
        with open(self.config_file, 'w') as f:
            json.dump(self.orientations, f, indent=2)
        print(f"[ORIENTATION] ✓ Sauvegardé dans {self.config_file}")
    
    def get_orientation(self, video_id: str) -> int:
        """
        Récupère l'orientation pour une vidéo
        
        Args:
            video_id: ID de la vidéo (nom sans extension)
            
        Returns:
            int: Rotation (0, 1, 2, ou 3)
        """
        return self.orientations.get(video_id, 0)
    
    def has_orientation(self, video_id: str) -> bool:
        """Vérifie si l'orientation est déjà configurée"""
        return video_id in self.orientations
    
    def detect_and_save(self, video_path: str, force: bool = False):
        """
        Affiche les 4 orientations et demande à l'utilisateur de choisir
        
        Args:
            video_path: Chemin de la vidéo
            force: Forcer la reconfiguration même si déjà fait
        """
        video_path = Path(video_path)
        video_id = video_path.stem
        
        # Vérifier si déjà configuré
        if not force and self.has_orientation(video_id):
            rotation = self.get_orientation(video_id)
            print(f"[ORIENTATION] ✓ {video_id}: déjà configuré à {rotation*90}°")
            return rotation
        
        print(f"\n{'='*70}")
        print(f"🔄 CONFIGURATION ORIENTATION: {video_id}")
        print('='*70)
        
        # Ouvrir vidéo
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            print(f"[ORIENTATION] ❌ Impossible d'ouvrir {video_path}")
            return 0
        
        # Prendre frame au milieu
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        middle_frame = total_frames // 2
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            print(f"[ORIENTATION] ❌ Impossible de lire la frame {middle_frame}")
            return 0
        
        # Créer les 4 versions
        orientations, zones = self._create_orientation_grid(frame)
        
        print("\nQuelle orientation est correcte ?")
        print("  • Cliquez sur l'image correcte")
        print("  • OU appuyez sur 0, 1, 2 ou 3 au clavier")
        print("  • ESC pour annuler")
        
        # Variable pour stocker le choix
        selected = [None]  # Liste pour pouvoir modifier dans callback
        
        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                # Déterminer quelle zone a été cliquée
                for zone_id, (x1, y1, x2, y2) in zones.items():
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        selected[0] = zone_id
                        cv2.destroyAllWindows()
                        break
        
        # Afficher avec callback souris
        cv2.namedWindow("Choisissez l'orientation correcte")
        cv2.setMouseCallback("Choisissez l'orientation correcte", mouse_callback)
        cv2.imshow("Choisissez l'orientation correcte", orientations)
        
        # Attendre choix (clic ou touche)
        while selected[0] is None:
            key = cv2.waitKey(100) & 0xFF
            
            # Touches 0-3
            if key == ord('0'):
                selected[0] = 0
                break
            elif key == ord('1'):
                selected[0] = 1
                break
            elif key == ord('2'):
                selected[0] = 2
                break
            elif key == ord('3'):
                selected[0] = 3
                break
            elif key == 27:  # ESC
                cv2.destroyAllWindows()
                print("❌ Annulé")
                return 0
        
        cv2.destroyAllWindows()
        
        if selected[0] is None:
            return 0
        
        rotation = selected[0]
        
        # Sauvegarder
        self.orientations[video_id] = rotation
        self.save_orientations()
        
        print(f"\n[ORIENTATION] ✓ {video_id} configuré à {rotation*90}°")
        
        return rotation
    
    def _create_orientation_grid(self, frame):
        """
        Crée une grille 2x2 avec les 4 orientations
        
        Returns:
            tuple: (Image avec les 4 orientations, dict des zones cliquables)
        """
        # Redimensionner pour que ça tienne à l'écran
        h, w = frame.shape[:2]
        max_size = 400
        
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            frame = cv2.resize(frame, None, fx=scale, fy=scale)
        
        h, w = frame.shape[:2]
        
        # Créer les 4 versions
        frames = []
        
        # 0° (original)
        frame_0 = frame.copy()
        # Ajouter bordure verte pour indiquer la zone cliquable
        cv2.rectangle(frame_0, (0, 0), (frame_0.shape[1]-1, frame_0.shape[0]-1), (0, 255, 0), 3)
        cv2.putText(frame_0, "0 - 0 degres", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame_0, "[Cliquez ici ou appuyez 0]", (10, frame_0.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        frames.append(frame_0)
        
        # 90°
        frame_90 = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        cv2.rectangle(frame_90, (0, 0), (frame_90.shape[1]-1, frame_90.shape[0]-1), (0, 255, 0), 3)
        cv2.putText(frame_90, "1 - 90 degres", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame_90, "[Cliquez ici ou appuyez 1]", (10, frame_90.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        frames.append(frame_90)
        
        # 180°
        frame_180 = cv2.rotate(frame, cv2.ROTATE_180)
        cv2.rectangle(frame_180, (0, 0), (frame_180.shape[1]-1, frame_180.shape[0]-1), (0, 255, 0), 3)
        cv2.putText(frame_180, "2 - 180 degres", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame_180, "[Cliquez ici ou appuyez 2]", (10, frame_180.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        frames.append(frame_180)
        
        # 270°
        frame_270 = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        cv2.rectangle(frame_270, (0, 0), (frame_270.shape[1]-1, frame_270.shape[0]-1), (0, 255, 0), 3)
        cv2.putText(frame_270, "3 - 270 degres", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(frame_270, "[Cliquez ici ou appuyez 3]", (10, frame_270.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        frames.append(frame_270)
        
        # Redimensionner pour que toutes aient la même taille
        max_h = max(f.shape[0] for f in frames)
        max_w = max(f.shape[1] for f in frames)
        
        resized = []
        for f in frames:
            # Créer canvas noir
            canvas = np.zeros((max_h, max_w, 3), dtype=np.uint8)
            # Centrer l'image
            y_offset = (max_h - f.shape[0]) // 2
            x_offset = (max_w - f.shape[1]) // 2
            canvas[y_offset:y_offset+f.shape[0], x_offset:x_offset+f.shape[1]] = f
            resized.append(canvas)
        
        # Créer grille 2x2
        top_row = np.hstack([resized[0], resized[1]])
        bottom_row = np.hstack([resized[2], resized[3]])
        grid = np.vstack([top_row, bottom_row])
        
        # Définir les zones cliquables (x1, y1, x2, y2)
        zones = {
            0: (0, 0, max_w, max_h),                           # Haut-gauche
            1: (max_w, 0, max_w * 2, max_h),                   # Haut-droite
            2: (0, max_h, max_w, max_h * 2),                   # Bas-gauche
            3: (max_w, max_h, max_w * 2, max_h * 2)           # Bas-droite
        }
        
        return grid, zones
    
    def rotate_frame(self, frame, rotation: int):
        """
        Applique une rotation à une frame
        
        Args:
            frame: Frame à tourner
            rotation: 0, 1, 2, ou 3
            
        Returns:
            Frame tournée
        """
        if rotation == 0:
            return frame
        elif rotation == 1:
            return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rotation == 2:
            return cv2.rotate(frame, cv2.ROTATE_180)
        elif rotation == 3:
            return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame


def configure_all_videos():
    """Configure l'orientation pour toutes les vidéos"""
    
    video_dir = Path("data/videos")
    videos = sorted(list(video_dir.glob("*.mp4")))
    
    if not videos:
        print("❌ Aucune vidéo trouvée dans data/videos/")
        return
    
    print("\n" + "=" * 70)
    print("🔄 CONFIGURATION DES ORIENTATIONS")
    print("=" * 70)
    print(f"\n{len(videos)} vidéo(s) à configurer")
    
    detector = ManualOrientationDetector()
    
    # Afficher l'état actuel
    configured = sum(1 for v in videos if detector.has_orientation(v.stem))
    print(f"Déjà configurées: {configured}/{len(videos)}")
    
    if configured == len(videos):
        response = input("\nToutes les vidéos sont déjà configurées. Reconfigurer ? (o/n) [n]: ").strip().lower()
        if response != 'o':
            print("\n✓ Utilisation de la configuration existante")
            detector.print_summary()
            return
    
    # Configurer chaque vidéo
    for i, video in enumerate(videos, 1):
        print(f"\n[{i}/{len(videos)}] {video.name}")
        
        force = False
        if detector.has_orientation(video.stem):
            response = input("  Déjà configurée. Reconfigurer ? (o/n) [n]: ").strip().lower()
            force = (response == 'o')
            if not force:
                continue
        
        detector.detect_and_save(str(video), force=force)
    
    # Résumé
    detector.print_summary()
    
    print("\n✅ Configuration terminée !")
    print(f"📁 Fichier: {detector.config_file}")


# Extension de la classe pour afficher le résumé
def print_summary(self):
    """Affiche un résumé des orientations configurées"""
    print("\n" + "=" * 70)
    print("📋 RÉSUMÉ DES ORIENTATIONS")
    print("=" * 70)
    
    if not self.orientations:
        print("Aucune orientation configurée")
        return
    
    # Grouper par rotation
    by_rotation = {0: [], 1: [], 2: [], 3: []}
    for video_id, rotation in sorted(self.orientations.items()):
        by_rotation[rotation].append(video_id)
    
    print(f"\nTotal: {len(self.orientations)} vidéo(s) configurée(s)")
    
    for rotation in [0, 1, 2, 3]:
        videos = by_rotation[rotation]
        if videos:
            print(f"\n{rotation*90}° ({len(videos)} vidéo(s)):")
            for video_id in videos:
                print(f"  • {video_id}")
    
    print("=" * 70)

ManualOrientationDetector.print_summary = print_summary


if __name__ == "__main__":
    configure_all_videos()