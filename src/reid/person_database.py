import csv
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict


class PersonDatabase:
    """Gestionnaire de la base de données des personnes (tracking intra-vidéo)"""
    
    def __init__(self, output_file="data/personnes.csv"):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Colonnes selon roadmap Jour 21
        self.columns = [
            "track_id",           # ID du track dans la vidéo
            "video_id",           # Vidéo source
            "frames_count",       # Nombre de frames
            "first_seen",         # Première apparition (frame)
            "last_seen",          # Dernière apparition (frame)
            # Colonnes bonus utiles
            "duration_seconds",   # Durée
            "avg_position_x",     # Position moyenne
            "avg_position_y",
        ]
    
    def extract_from_trajectories(self, trajectory_dir="data/trajectories"):
        """
        Extrait personnes depuis trajectoires (1 track = 1 personne pour l'instant)
        
        Args:
            trajectory_dir: Dossier contenant les trajectoires JSON
            
        Returns:
            list: Liste de personnes avec leurs infos
        """
        trajectory_dir = Path(trajectory_dir)
        traj_files = list(trajectory_dir.glob("*.json"))
        
        if not traj_files:
            print(f"[PERSON DB] ⚠️  Aucune trajectoire trouvée dans {trajectory_dir}")
            return []
        
        print(f"[PERSON DB] 📊 Extraction depuis {len(traj_files)} fichier(s)...")
        
        all_persons = []
        
        for traj_file in traj_files:
            try:
                with open(traj_file, 'r') as f:
                    data = json.load(f)
                
                video_id = data.get("video_id", traj_file.stem)
                trajectories = data.get("trajectories", [])
                
                for traj in trajectories:
                    person = self._process_trajectory(traj, video_id)
                    
                    if person:
                        all_persons.append(person)
                
                print(f"[PERSON DB]   ✓ {video_id}: {len(trajectories)} personne(s)")
                
            except Exception as e:
                print(f"[PERSON DB]   ✗ Erreur {traj_file.name}: {e}")
        
        print(f"[PERSON DB] ✓ Total: {len(all_persons)} personne(s) extraites")
        return all_persons
    
    def _extract_camera_id(self, video_id):
        """Extrait l'ID de la caméra depuis le nom de la vidéo"""
        # Exemples: CAMERA_HALL_PORTE_ENTREE -> HALL_PORTE_ENTREE
        if video_id.startswith("CAMERA_"):
            return video_id[7:]  # Enlever "CAMERA_"
        return video_id
    
    def _process_trajectory(self, traj, video_id):
        """
        Traite une trajectoire (format roadmap Jour 21)
        
        Args:
            traj: Dictionnaire trajectoire
            video_id: ID de la vidéo
            
        Returns:
            dict: Infos de la personne
        """
        try:
            track_id = traj.get("track_id")
            frames = traj.get("frames", [])
            
            if not frames:
                return None
            
            # Infos selon roadmap
            first_frame = frames[0]
            last_frame = frames[-1]
            
            frames_count = len(frames)
            first_seen = first_frame["frame"]
            last_seen = last_frame["frame"]
            
            # Calculs bonus
            positions = [(f["x"], f["y"]) for f in frames]
            avg_x = int(sum(p[0] for p in positions) / len(positions))
            avg_y = int(sum(p[1] for p in positions) / len(positions))
            
            first_time = first_frame.get("t", 0)
            last_time = last_frame.get("t", 0)
            duration_seconds = round(last_time - first_time, 2) if last_time > first_time else 0
            
            return {
                "track_id": track_id,
                "video_id": video_id,
                "frames_count": frames_count,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "duration_seconds": duration_seconds,
                "avg_position_x": avg_x,
                "avg_position_y": avg_y
            }
            
        except Exception as e:
            print(f"[PERSON DB] ⚠️  Erreur traitement: {e}")
            return None
    
    def save_to_csv(self, persons):
        """Sauvegarde selon format roadmap"""
        if not persons:
            print("[PERSON DB] ⚠️  Aucune personne à sauvegarder")
            return
        
        try:
            with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.columns)
                writer.writeheader()
                writer.writerows(persons)
            
            file_size = self.output_file.stat().st_size / 1024
            
            print(f"[PERSON DB] ✓ Sauvegardé: {self.output_file}")
            print(f"[PERSON DB] ✓ {len(persons)} personne(s)")
            print(f"[PERSON DB] ✓ Taille: {file_size:.1f} KB")
            
        except Exception as e:
            print(f"[PERSON DB] ✗ Erreur: {e}")
    
    def load_from_csv(self):
        """
        Charge la base de personnes depuis le CSV
        
        Returns:
            list: Liste de dictionnaires personnes
        """
        if not self.output_file.exists():
            print(f"[PERSON DB] ⚠️  Fichier {self.output_file} n'existe pas")
            return []
        
        try:
            with open(self.output_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                persons = list(reader)
            
            print(f"[PERSON DB] ✓ Chargé: {len(persons)} personne(s)")
            return persons
            
        except Exception as e:
            print(f"[PERSON DB] ✗ Erreur chargement: {e}")
            return []
    
    def get_stats(self, detections=None):
        """
        Calcule des statistiques sur la base de détections
        
        Args:
            detections: Liste de détections (charge depuis CSV si None)
            
        Returns:
            dict: Statistiques
        """
        if detections is None:
            detections = self.load_from_csv()
        
        if not detections:
            return {}
        
        # Grouper par caméra
        by_camera = {}
        for d in detections:
            cam = d["camera_id"]
            if cam not in by_camera:
                by_camera[cam] = []
            by_camera[cam].append(d)
        
        # Statistiques globales
        total_frames = sum(int(d["frames_count"]) for d in detections)
        total_distance = sum(int(d["total_distance"]) for d in detections)
        
        avg_frames = total_frames / len(detections)
        avg_distance = total_distance / len(detections)
        
        # Détections courtes vs longues
        short_detections = [d for d in detections if int(d["frames_count"]) < 30]
        long_detections = [d for d in detections if int(d["frames_count"]) >= 100]
        
        return {
            "total_detections": len(detections),
            "total_cameras": len(by_camera),
            "cameras": {cam: len(dets) for cam, dets in by_camera.items()},
            "avg_frames_per_detection": round(avg_frames, 1),
            "avg_distance_per_detection": round(avg_distance, 1),
            "total_frames_tracked": total_frames,
            "total_distance_tracked": total_distance,
            "short_detections": len(short_detections),
            "long_detections": len(long_detections)
        }
    
    def print_stats(self, detections=None):
        """Affiche les statistiques"""
        stats = self.get_stats(detections)
        
        if not stats:
            print("[DETECTION DB] Aucune statistique disponible")
            return
        
        print("\n" + "=" * 70)
        print("📊 STATISTIQUES BASE DÉTECTIONS")
        print("=" * 70)
        print(f"Total détections: {stats['total_detections']}")
        print(f"  └─ Courtes (< 30 frames): {stats['short_detections']}")
        print(f"  └─ Longues (≥ 100 frames): {stats['long_detections']}")
        print(f"\nCaméras actives: {stats['total_cameras']}")
        print(f"Frames moyennes/détection: {stats['avg_frames_per_detection']}")
        print(f"Distance moyenne/détection: {stats['avg_distance_per_detection']} px")
        
        print("\n" + "-" * 70)
        print("Détections par caméra:")
        print("-" * 70)
        for cam, count in sorted(stats["cameras"].items(), key=lambda x: -x[1]):
            print(f"  {cam}: {count} détection(s)")
        
        print("\n" + "-" * 70)
        print("ℹ️  Note: Une même personne peut apparaître dans plusieurs détections")
        print("   (passages multiples, caméras différentes)")
        print("=" * 70)
    
    def build_database(self, trajectory_dir="data/trajectories"):
        """Construit la base personnes (Milestone 3)"""
        print("\n" + "=" * 70)
        print("🏗️  CONSTRUCTION BASE PERSONNES (Milestone 3 - Jour 21)")
        print("=" * 70)
        
        persons = self.extract_from_trajectories(trajectory_dir)
        
        if persons:
            self.save_to_csv(persons)
            self.print_stats(persons)
        
        print("\nℹ️  Note: La ré-identification viendra en SEMAINE 5")
        print("=" * 70)
        
        return persons


# Point d'entrée
if __name__ == "__main__":
    db = PersonDatabase()
    db.build_database()