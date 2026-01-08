"""
Création de zones avec même timestamp sur toutes les vidéos
Utilise les orientations enregistrées
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zone_manager import ZoneManager
from utils.orientation import ManualOrientationDetector


class UnifiedZoneEditor:
    """Éditeur de zones unifié avec même timestamp"""
    
    def __init__(self, timestamp_seconds=62, display_width=1280):
        """
        Args:
            timestamp_seconds: Timestamp à utiliser pour toutes les vidéos (défaut: 1min 2sec)
            display_width: Largeur d'affichage en pixels (défaut: 1280)
        """
        self.timestamp_seconds = timestamp_seconds
        self.display_width = display_width
        self.orientation_detector = ManualOrientationDetector()
        self.zone_manager = ZoneManager()
        self.zone_counter = 1
    
    def resize_frame(self, frame):
        """
        Redimensionne la frame pour tenir dans l'écran
        
        Args:
            frame: Frame à redimensionner
            
        Returns:
            tuple: (frame redimensionnée, facteur d'échelle)
        """
        h, w = frame.shape[:2]
        
        if w > self.display_width:
            scale = self.display_width / w
            new_w = self.display_width
            new_h = int(h * scale)
            resized = cv2.resize(frame, (new_w, new_h))
            return resized, scale
        
        return frame, 1.0
    
    def get_frame_at_timestamp(self, video_path: str):
        """
        Récupère la frame à un timestamp donné avec la bonne orientation
        
        Args:
            video_path: Chemin de la vidéo
            
        Returns:
            tuple: (frame, fps, scale) ou (None, None, None) si erreur
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None, None, None
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Calculer le numéro de frame
        target_frame = int(self.timestamp_seconds * fps)
        
        # Vérifier que la frame existe
        if target_frame >= total_frames:
            # Prendre la frame du milieu si timestamp trop grand
            target_frame = total_frames // 2
            print(f"  ⚠️  Timestamp trop grand, utilisation frame {target_frame}")
        
        # Aller à la frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return None, None, None
        
        # Appliquer l'orientation enregistrée
        video_id = Path(video_path).stem
        rotation = self.orientation_detector.get_orientation(video_id)
        
        if rotation > 0:
            frame = self.orientation_detector.rotate_frame(frame, rotation)
            print(f"  🔄 Rotation appliquée: {rotation * 90}°")
        
        # Redimensionner
        frame, scale = self.resize_frame(frame)
        
        return frame, fps, scale
    
    def create_zone_on_video(self, video_path: str, zone_id: str, zone_name: str):
        """
        Crée une zone sur une vidéo
        
        Args:
            video_path: Chemin de la vidéo
            zone_id: ID de la zone
            zone_name: Nom de la zone
            
        Returns:
            dict: Données de la zone ou None
        """
        video_path = Path(video_path)
        camera_id = video_path.stem.replace("CAMERA_", "")
        
        print(f"\n{'='*70}")
        print(f"📹 {video_path.name}")
        print(f"   Caméra: {camera_id}")
        print(f"   Timestamp: {self.timestamp_seconds}s ({self.timestamp_seconds//60}min {self.timestamp_seconds%60}s)")
        print('='*70)
        
        # Charger la frame
        frame, fps, scale = self.get_frame_at_timestamp(str(video_path))
        
        if frame is None:
            print("  ❌ Impossible de charger la frame")
            return None
        
        # Afficher la frame dans une fenêtre
        window_name = f"Vidéo - {video_path.name}"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        
        # Ajouter les instructions sur l'image
        display_frame = frame.copy()
        cv2.putText(display_frame, "C = Creer zone | S = Sauter | Q/ESC = Quitter", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(window_name, display_frame)
        
        # Instructions terminal
        print("\n👁️  Vidéo affichée ! Appuyez sur :")
        print("  C = Créer une zone sur cette caméra")
        print("  S = Sauter cette caméra")
        print("  Q ou ESC = Quitter")
        
        # Attendre le choix (uniquement via clavier dans la fenêtre)
        choice = None
        while True:
            key = cv2.waitKey(0) & 0xFF
            
            if key == ord('c') or key == ord('C'):
                choice = 'c'
                break
            elif key == ord('s') or key == ord('S'):
                choice = 's'
                break
            elif key == ord('q') or key == ord('Q') or key == 27:  # ESC
                choice = 'q'
                break
        
        # Fermer la fenêtre de prévisualisation
        cv2.destroyWindow(window_name)
        
        if choice == 'q':
            return 'quit'
        
        if choice != 'c':
            print("  → Vidéo ignorée")
            return None
        
        # Créer la zone
        editor = ZoneEditor(frame, zone_id, zone_name, camera_id, scale)
        zone_data = editor.edit()
        
        if zone_data:
            print(f"\n  ✓ Zone '{zone_name}' créée sur {camera_id}")
            return zone_data
        else:
            print(f"\n  ✗ Création annulée")
            return None


class ZoneEditor:
    """Éditeur visuel de zone"""
    
    def __init__(self, frame, zone_id: str, zone_name: str, camera_id: str, scale: float = 1.0):
        self.frame = frame
        self.zone_id = zone_id
        self.zone_name = zone_name
        self.camera_id = camera_id
        self.scale = scale
        self.points = []
        self.display = None
    
    def mouse_callback(self, event, x, y, flags, param):
        """Callback souris"""
        if event == cv2.EVENT_LBUTTONDOWN:
            # Convertir les coordonnées à l'échelle originale
            original_x = int(x / self.scale)
            original_y = int(y / self.scale)
            self.points.append((original_x, original_y))
            print(f"  Point {len(self.points)}: ({original_x}, {original_y})")
            self.draw()
        
        elif event == cv2.EVENT_RBUTTONDOWN and self.points:
            removed = self.points.pop()
            print(f"  Point retiré: {removed}")
            self.draw()
    
    def draw(self):
        """Dessine l'interface"""
        self.display = self.frame.copy()
        
        # Dessiner les points (à l'échelle d'affichage)
        for i, (px, py) in enumerate(self.points):
            display_x = int(px * self.scale)
            display_y = int(py * self.scale)
            cv2.circle(self.display, (display_x, display_y), 5, (0, 0, 255), -1)
            cv2.putText(
                self.display, str(i + 1),
                (display_x + 8, display_y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 0, 255), 2
            )
        
        # Dessiner le polygone
        if len(self.points) > 1:
            display_points = [(int(px * self.scale), int(py * self.scale)) for px, py in self.points]
            pts = np.array(display_points, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(
                self.display, [pts],
                isClosed=len(self.points) >= 3,
                color=(0, 0, 255),
                thickness=2
            )
        
        # Instructions
        cv2.putText(self.display, f"{self.zone_name}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.putText(self.display, f"Camera: {self.camera_id}", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(self.display,
                   "Clic gauche: Ajouter | Clic droit: Retirer | ENTER: Valider | ESC: Annuler",
                   (10, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Compteur de points
        status = f"Points: {len(self.points)}/4 minimum"
        color = (0, 255, 0) if len(self.points) >= 4 else (0, 165, 255)
        cv2.putText(self.display, status, (10, 120),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        cv2.imshow("Zone Editor", self.display)
    
    def edit(self):
        """Lance l'éditeur"""
        print(f"\n  🖊️  Créez la zone en cliquant sur les coins")
        print(f"     Minimum 4 points requis")
        
        cv2.namedWindow("Zone Editor", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("Zone Editor", self.mouse_callback)
        
        self.draw()
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            
            if key == 13:  # ENTER
                if len(self.points) >= 4:
                    cv2.destroyAllWindows()
                    return {
                        "zone_id": self.zone_id,
                        "name": self.zone_name,
                        "camera_id": self.camera_id,
                        "polygon": self.points
                    }
                else:
                    print(f"  ⚠️  Il faut au moins 4 points (vous en avez {len(self.points)})")
            
            elif key == 27:  # ESC
                cv2.destroyAllWindows()
                return None


def main():
    """Point d'entrée principal"""
    
    print("\n" + "=" * 70)
    print("🚨 CRÉATION DE ZONES UNIFIÉES")
    print("=" * 70)
    print("\nCe script va afficher toutes les vidéos au même timestamp (1min 2sec)")
    print("Vous pouvez créer une zone ou passer à la suivante")
    print("Pratique pour définir la même zone sur plusieurs caméras !")
    print("=" * 70)
    
    # Vérifier les orientations
    orientation_detector = ManualOrientationDetector()
    if not orientation_detector.orientations:
        print("\n❌ Aucune orientation configurée !")
        print("   Lancez d'abord: python configure_orientations.py")
        return
    
    print(f"\n✓ {len(orientation_detector.orientations)} orientation(s) configurée(s)")
    
    # Paramètres
    timestamp = input("\nTimestamp à utiliser (secondes) [62]: ").strip()
    timestamp = int(timestamp) if timestamp else 62
    
    display_width = input("Largeur d'affichage (pixels) [1280]: ").strip()
    display_width = int(display_width) if display_width else 1280
    
    print(f"\n✓ Utilisation du timestamp: {timestamp}s ({timestamp//60}min {timestamp%60}s)")
    print(f"✓ Largeur d'affichage: {display_width}px")
    
    # Lister les vidéos
    video_dir = Path("data/videos")
    videos = sorted(list(video_dir.glob("*.mp4")))
    
    if not videos:
        print("\n❌ Aucune vidéo trouvée dans data/videos/")
        return
    
    print(f"\n✓ {len(videos)} vidéo(s) trouvée(s)")
    
    # Initialiser l'éditeur
    editor = UnifiedZoneEditor(timestamp_seconds=timestamp, display_width=display_width)
    
    # Traiter chaque vidéo
    zones_created = []
    
    for i, video_path in enumerate(videos, 1):
        print(f"\n{'='*70}")
        print(f"[{i}/{len(videos)}]")
        
        zone_id = f"ZONE_{editor.zone_counter}"
        zone_name = f"Zone Interdite {editor.zone_counter}"
        
        result = editor.create_zone_on_video(str(video_path), zone_id, zone_name)
        
        if result == 'quit':
            print("\n⏸️  Arrêt demandé")
            break
        
        if result:
            # Sauvegarder la zone
            editor.zone_manager.create_zone(
                zone_id=result["zone_id"],
                name=result["name"],
                camera_id=result["camera_id"],
                polygon_points=result["polygon"],
                description=f"Zone créée au timestamp {timestamp}s"
            )
            zones_created.append(result)
            editor.zone_counter += 1
    
    # Sauvegarder toutes les zones
    if zones_created:
        editor.zone_manager.save_zones()
        editor.zone_manager.print_summary()
        
        print(f"\n✅ {len(zones_created)} zone(s) créée(s) avec succès !")
        print(f"📁 Fichier: data/zones_interdites.json")
    else:
        print("\n⚠️  Aucune zone créée")


if __name__ == "__main__":
    main()