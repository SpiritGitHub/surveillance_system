"""
Visualiseur multi-caméras - Affiche toutes les vidéos en même temps
Synchronisées au même timestamp de départ
"""

import cv2
import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.orientation import ManualOrientationDetector


class MultiVideoViewer:
    """Affiche plusieurs vidéos en grille avec synchronisation"""
    
    def __init__(self, start_timestamp=0, max_display_width=1920, max_display_height=1080):
        """
        Args:
            start_timestamp: Timestamp de départ en secondes (toutes les vidéos démarrent ici)
            max_display_width: Largeur max de l'écran
            max_display_height: Hauteur max de l'écran
        """
        self.start_timestamp = start_timestamp
        self.max_display_width = max_display_width
        self.max_display_height = max_display_height
        self.orientation_detector = ManualOrientationDetector()
        self.caps = []
        self.video_info = []
        self.paused = False
        self.cell_width = 320
        self.cell_height = 240
        self.grid_cols = 4
        self.grid_rows = 3
    
    def calculate_optimal_layout(self, n_videos):
        """Calcule la meilleure disposition pour les vidéos"""
        # Essayer différentes configurations
        best_layout = None
        best_cell_size = 0
        
        # Tester différents nombres de colonnes
        for cols in range(2, n_videos + 1):
            rows = (n_videos + cols - 1) // cols
            
            # Calculer la taille des cellules pour cette config
            cell_w = (self.max_display_width - 20) // cols  # 20px de marge
            cell_h = (self.max_display_height - 60) // rows  # 60px de marge + contrôles
            
            # Prendre le minimum pour garder le ratio
            cell_size = min(cell_w, cell_h)
            
            # Garder la meilleure config (celle avec les plus grandes cellules)
            if cell_size > best_cell_size:
                best_cell_size = cell_size
                best_layout = (cols, rows, cell_size)
        
        return best_layout
    
    def load_videos(self, video_paths):
        """Charge toutes les vidéos et les synchronise au timestamp de départ"""
        print(f"\n📹 Chargement de {len(video_paths)} vidéo(s)...")
        print(f"🔄 Synchronisation au timestamp: {self.start_timestamp}s ({self.start_timestamp//60}min {self.start_timestamp%60}s)")
        
        for i, video_path in enumerate(video_paths, 1):
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                print(f"  ❌ Impossible d'ouvrir: {video_path.name}")
                continue
            
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps
            
            # Aller au timestamp de départ (SYNCHRONISATION)
            target_frame = int(self.start_timestamp * fps)
            if target_frame >= total_frames:
                print(f"  ⚠️  {video_path.name}: timestamp trop grand, démarrage au milieu")
                target_frame = total_frames // 2
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            
            video_id = Path(video_path).stem
            rotation = self.orientation_detector.get_orientation(video_id)
            
            self.caps.append(cap)
            self.video_info.append({
                'name': video_path.name,
                'video_id': video_id,
                'rotation': rotation,
                'fps': fps,
                'total_frames': total_frames,
                'duration': duration,
                'start_frame': target_frame
            })
            
            print(f"  ✓ [{i}] {video_path.name} - Démarrage: {self.start_timestamp}s - Rotation: {rotation*90}°")
        
        print(f"\n✅ {len(self.caps)} vidéo(s) chargée(s) et synchronisées")
        
        # Calculer la disposition optimale
        if self.caps:
            cols, rows, cell_size = self.calculate_optimal_layout(len(self.caps))
            self.grid_cols = cols
            self.grid_rows = rows
            self.cell_width = cell_size
            self.cell_height = cell_size
            
            print(f"\n📐 Disposition optimale: {cols} colonnes × {rows} lignes")
            print(f"   Taille des cellules: {cell_size}×{cell_size}px")
            print(f"   Taille totale: {cols*cell_size}×{rows*cell_size}px")
        
        return len(self.caps) > 0
    
    def resize_and_rotate_frame(self, frame, rotation):
        """Redimensionne et applique la rotation"""
        if frame is None:
            return None
        
        # Appliquer rotation
        if rotation > 0:
            frame = self.orientation_detector.rotate_frame(frame, rotation)
        
        # Redimensionner en gardant le ratio
        h, w = frame.shape[:2]
        
        # Calculer le ratio pour remplir la cellule
        ratio = min(self.cell_width / w, self.cell_height / h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        
        resized = cv2.resize(frame, (new_w, new_h))
        
        # Centrer dans une cellule de taille fixe
        result = np.zeros((self.cell_height, self.cell_width, 3), dtype=np.uint8)
        
        # Calculer le décalage pour centrer
        x_offset = (self.cell_width - new_w) // 2
        y_offset = (self.cell_height - new_h) // 2
        
        result[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        
        return result
    
    def create_grid(self, frames):
        """Crée une grille avec toutes les frames"""
        if not frames:
            return None
        
        n_videos = len(frames)
        
        # Créer les lignes
        rows = []
        for row_idx in range(self.grid_rows):
            row_frames = []
            
            for col_idx in range(self.grid_cols):
                video_idx = row_idx * self.grid_cols + col_idx
                
                if video_idx < n_videos and frames[video_idx] is not None:
                    frame = frames[video_idx].copy()
                    
                    # Ajouter le nom de la vidéo en haut
                    name = self.video_info[video_idx]['name'].replace('.mp4', '').replace('.MP4', '')
                    name_short = name[:30] if len(name) > 30 else name
                    
                    # Fond noir pour le texte
                    cv2.rectangle(frame, (0, 0), (self.cell_width, 25), (0, 0, 0), -1)
                    cv2.putText(frame, name_short, (5, 18),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    
                    row_frames.append(frame)
                else:
                    # Frame noire si pas de vidéo
                    blank = np.zeros((self.cell_height, self.cell_width, 3), dtype=np.uint8)
                    row_frames.append(blank)
            
            # Concaténer horizontalement
            row_img = np.hstack(row_frames)
            rows.append(row_img)
        
        # Concaténer verticalement
        grid = np.vstack(rows)
        
        # Ajouter une barre de contrôle en bas
        control_bar = np.zeros((40, grid.shape[1], 3), dtype=np.uint8)
        
        # Afficher les contrôles
        if self.paused:
            status = "⏸ PAUSE"
            color = (0, 255, 255)
        else:
            status = "▶ LECTURE"
            color = (0, 255, 0)
        
        cv2.putText(control_bar, status, (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        cv2.putText(control_bar, "ESPACE: Pause | ←→: ±5s | Q/ESC: Quitter", (200, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Ajouter le timestamp actuel
        if self.caps:
            current_pos = self.caps[0].get(cv2.CAP_PROP_POS_FRAMES)
            current_time = current_pos / self.video_info[0]['fps']
            time_str = f"T: {int(current_time//60):02d}:{int(current_time%60):02d}"
            cv2.putText(control_bar, time_str, (grid.shape[1] - 100, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        # Combiner grille + barre de contrôle
        result = np.vstack([grid, control_bar])
        
        return result
    
    def show_video_mode(self):
        """Mode vidéo: lit toutes les vidéos en temps réel de manière synchronisée"""
        print("\n🎬 Mode Lecture Vidéo Synchronisée")
        print("\n⌨️  Contrôles:")
        print("  ESPACE = Pause/Play")
        print("  ESC ou Q = Quitter")
        print("  ← → = Reculer/Avancer de 5 secondes (toutes les vidéos ensemble)")
        print("\n▶️  Lecture démarrée...\n")
        
        cv2.namedWindow("Multi-Cameras Synchronisees", cv2.WINDOW_NORMAL)
        
        frame_count = 0
        
        while True:
            if not self.paused:
                frames = []
                all_ended = True
                
                for i, cap in enumerate(self.caps):
                    ret, frame = cap.read()
                    if ret:
                        all_ended = False
                        frame = self.resize_and_rotate_frame(frame, self.video_info[i]['rotation'])
                        frames.append(frame)
                    else:
                        # Si vidéo terminée, afficher écran noir
                        blank = np.zeros((self.cell_height, self.cell_width, 3), dtype=np.uint8)
                        cv2.putText(blank, "FIN", (self.cell_width//2 - 30, self.cell_height//2),
                                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                        frames.append(blank)
                
                if all_ended:
                    print("\n✅ Toutes les vidéos sont terminées")
                    break
                
                grid = self.create_grid(frames)
                if grid is not None:
                    cv2.imshow("Multi-Cameras Synchronisees", grid)
                
                frame_count += 1
            else:
                # En pause, juste attendre
                pass
            
            # Contrôles
            key = cv2.waitKey(30 if not self.paused else 100) & 0xFF
            
            if key == 27 or key == ord('q') or key == ord('Q'):  # ESC ou Q
                break
            elif key == 32:  # ESPACE
                self.paused = not self.paused
                print("⏸️  PAUSE" if self.paused else "▶️  LECTURE")
            elif key == 81 or key == 2:  # Flèche gauche
                self.seek_all(-5)
                print("⏪ -5 secondes")
            elif key == 83 or key == 3:  # Flèche droite
                self.seek_all(5)
                print("⏩ +5 secondes")
        
        self.cleanup()
    
    def seek_all(self, seconds):
        """Déplace toutes les vidéos de X secondes (garde la synchronisation)"""
        for i, cap in enumerate(self.caps):
            current_frame = cap.get(cv2.CAP_PROP_POS_FRAMES)
            fps = self.video_info[i]['fps']
            new_frame = max(0, current_frame + seconds * fps)
            new_frame = min(new_frame, self.video_info[i]['total_frames'] - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, new_frame)
    
    def cleanup(self):
        """Libère les ressources"""
        for cap in self.caps:
            cap.release()
        cv2.destroyAllWindows()
        print("\n👋 Fermeture...")


def main():
    """Point d'entrée"""
    print("\n" + "=" * 70)
    print("📹 VISUALISEUR MULTI-CAMÉRAS SYNCHRONISÉES")
    print("=" * 70)
    
    # Charger les vidéos
    video_dir = Path("data/videos")
    videos = sorted(list(video_dir.glob("*.mp4")))
    
    if not videos:
        print("\n❌ Aucune vidéo trouvée dans data/videos/")
        return
    
    print(f"\n✓ {len(videos)} vidéo(s) trouvée(s)")
    
    # Paramètres
    print("\n⚙️  Configuration:")
    
    timestamp_input = input("\nTimestamp de départ pour TOUTES les vidéos (secondes) [0]: ").strip()
    start_timestamp = int(timestamp_input) if timestamp_input else 0
    
    width_input = input("\nLargeur maximale d'affichage (pixels) [1920]: ").strip()
    max_width = int(width_input) if width_input else 1920
    
    height_input = input("\nHauteur maximale d'affichage (pixels) [1080]: ").strip()
    max_height = int(height_input) if height_input else 1080
    
    print(f"\n✓ Timestamp de départ: {start_timestamp}s ({start_timestamp//60}min {start_timestamp%60}s)")
    print(f"✓ Résolution max: {max_width}×{max_height}px")
    
    # Créer le visualiseur
    viewer = MultiVideoViewer(
        start_timestamp=start_timestamp,
        max_display_width=max_width,
        max_display_height=max_height
    )
    
    # Charger les vidéos
    if not viewer.load_videos(videos):
        print("\n❌ Aucune vidéo n'a pu être chargée")
        return
    
    # Lancer l'affichage
    viewer.show_video_mode()


if __name__ == "__main__":
    main()