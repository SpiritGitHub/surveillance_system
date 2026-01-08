"""
Validateur de trajectoires
Vérifie si les fichiers sont complets et valides
"""

import json
from pathlib import Path
from enum import Enum


class TrajectoryStatus(Enum):
    """Statut d'une trajectoire"""
    COMPLETE = "complete"           # Tout est bon
    INCOMPLETE = "incomplete"       # Existe mais incomplet
    MISSING = "missing"            # N'existe pas
    CORRUPTED = "corrupted"        # Existe mais corrompu


class TrajectoryValidator:
    """Validateur de trajectoires avec reprise intelligente"""
    
    def __init__(self, trajectory_dir="data/trajectories"):
        self.trajectory_dir = Path(trajectory_dir)
        self.trajectory_dir.mkdir(parents=True, exist_ok=True)
    
    def check_video(self, video_path, min_frames=100):
        """
        Vérifie le statut d'une vidéo
        
        Args:
            video_path: Chemin de la vidéo
            min_frames: Nombre minimum de frames attendues
            
        Returns:
            dict: {
                "status": TrajectoryStatus,
                "reason": str,
                "needs_processing": bool,
                "trajectory_file": Path ou None
            }
        """
        video_path = Path(video_path)
        video_id = video_path.stem
        traj_file = self.trajectory_dir / f"{video_id}.json"
        
        # 1. Fichier n'existe pas
        if not traj_file.exists():
            return {
                "status": TrajectoryStatus.MISSING,
                "reason": "Fichier de trajectoire absent",
                "needs_processing": True,
                "trajectory_file": None,
                "can_resume": False
            }
        
        # 2. Essayer de lire le fichier
        try:
            with open(traj_file, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            return {
                "status": TrajectoryStatus.CORRUPTED,
                "reason": "Fichier JSON corrompu",
                "needs_processing": True,
                "trajectory_file": traj_file,
                "can_resume": False
            }
        except Exception as e:
            return {
                "status": TrajectoryStatus.CORRUPTED,
                "reason": f"Erreur lecture: {str(e)}",
                "needs_processing": True,
                "trajectory_file": traj_file,
                "can_resume": False
            }
        
        # 3. Vérifier la structure
        if not isinstance(data, dict):
            return {
                "status": TrajectoryStatus.CORRUPTED,
                "reason": "Structure invalide (pas un dict)",
                "needs_processing": True,
                "trajectory_file": traj_file,
                "can_resume": False
            }
        
        # 4. Vérifier les champs essentiels
        required_fields = ["video_id", "stats", "trajectories"]
        missing_fields = [f for f in required_fields if f not in data]
        
        if missing_fields:
            return {
                "status": TrajectoryStatus.INCOMPLETE,
                "reason": f"Champs manquants: {missing_fields}",
                "needs_processing": True,
                "trajectory_file": traj_file,
                "can_resume": False
            }
        
        # 5. Vérifier que le traitement est complet
        stats = data.get("stats", {})
        frames_processed = stats.get("frames_processed", 0)
        
        if frames_processed < min_frames:
            return {
                "status": TrajectoryStatus.INCOMPLETE,
                "reason": f"Seulement {frames_processed} frames traitées (< {min_frames})",
                "needs_processing": True,
                "trajectory_file": traj_file,
                "can_resume": False,
                "frames_done": frames_processed
            }
        
        # 6. Vérifier que le fichier n'est pas vide
        trajectories = data.get("trajectories", [])
        file_size = traj_file.stat().st_size
        
        if file_size < 100:  # Moins de 100 bytes = suspect
            return {
                "status": TrajectoryStatus.INCOMPLETE,
                "reason": f"Fichier trop petit ({file_size} bytes)",
                "needs_processing": True,
                "trajectory_file": traj_file,
                "can_resume": False
            }
        
        # 7. TOUT EST BON !
        return {
            "status": TrajectoryStatus.COMPLETE,
            "reason": f"Complet: {len(trajectories)} trajectoires, {frames_processed} frames",
            "needs_processing": False,
            "trajectory_file": traj_file,
            "can_resume": False,
            "num_trajectories": len(trajectories),
            "frames_processed": frames_processed,
            "file_size_kb": file_size / 1024
        }
    
    def scan_all_videos(self, video_dir="data/videos"):
        """
        Scanne toutes les vidéos et retourne le statut
        
        Returns:
            dict: {
                "complete": [video_paths],
                "missing": [video_paths],
                "incomplete": [video_paths],
                "corrupted": [video_paths],
                "summary": {...}
            }
        """
        video_dir = Path(video_dir)
        all_videos = list(video_dir.glob("*.mp4"))
        
        # Dédupliquer par stem (nom sans extension)
        seen_stems = {}
        videos = []
        for v in all_videos:
            stem = v.stem.lower()  # Normaliser en minuscules
            if stem not in seen_stems:
                seen_stems[stem] = v
                videos.append(v)
            # Sinon c'est un doublon, on l'ignore
        
        results = {
            "complete": [],
            "missing": [],
            "incomplete": [],
            "corrupted": []
        }
        
        for video_path in videos:
            check = self.check_video(video_path)
            status = check["status"]
            
            if status == TrajectoryStatus.COMPLETE:
                results["complete"].append({
                    "video": video_path,
                    "info": check
                })
            elif status == TrajectoryStatus.MISSING:
                results["missing"].append({
                    "video": video_path,
                    "info": check
                })
            elif status == TrajectoryStatus.INCOMPLETE:
                results["incomplete"].append({
                    "video": video_path,
                    "info": check
                })
            elif status == TrajectoryStatus.CORRUPTED:
                results["corrupted"].append({
                    "video": video_path,
                    "info": check
                })
        
        results["summary"] = {
            "total": len(videos),
            "complete": len(results["complete"]),
            "missing": len(results["missing"]),
            "incomplete": len(results["incomplete"]),
            "corrupted": len(results["corrupted"]),
            "needs_processing": len(results["missing"]) + len(results["incomplete"]) + len(results["corrupted"])
        }
        
        return results
    
    def get_videos_to_process(self, video_dir="data/videos", force_reprocess=False):
        """
        Retourne la liste des vidéos à traiter
        
        Args:
            video_dir: Dossier des vidéos
            force_reprocess: Forcer le retraitement même si complet
            
        Returns:
            list: Vidéos à traiter
        """
        if force_reprocess:
            video_dir = Path(video_dir)
            return list(video_dir.glob("*.mp4"))
        
        scan = self.scan_all_videos(video_dir)
        
        to_process = []
        
        # Ajouter les manquantes
        to_process.extend([item["video"] for item in scan["missing"]])
        
        # Ajouter les incomplètes
        to_process.extend([item["video"] for item in scan["incomplete"]])
        
        # Ajouter les corrompues
        to_process.extend([item["video"] for item in scan["corrupted"]])
        
        return to_process
    
    def print_scan_report(self, video_dir="data/videos"):
        """Affiche un rapport détaillé"""
        scan = self.scan_all_videos(video_dir)
        
        print("\n" + "=" * 70)
        print("📊 RAPPORT DE VÉRIFICATION")
        print("=" * 70)
        
        summary = scan["summary"]
        print(f"\n✅ Complètes:   {summary['complete']}/{summary['total']}")
        print(f"❌ Manquantes:  {summary['missing']}/{summary['total']}")
        print(f"⚠️  Incomplètes: {summary['incomplete']}/{summary['total']}")
        print(f"🔴 Corrompues:  {summary['corrupted']}/{summary['total']}")
        print(f"\n📝 À traiter:   {summary['needs_processing']}/{summary['total']}")
        
        # Détails des complètes
        if scan["complete"]:
            print("\n" + "-" * 70)
            print("✅ VIDÉOS COMPLÈTES (ignorées)")
            print("-" * 70)
            for item in scan["complete"][:5]:  # Montrer seulement les 5 premières
                info = item["info"]
                print(f"  ✓ {item['video'].name}")
                print(f"    → {info['num_trajectories']} trajectoires, {info['frames_processed']} frames, {info['file_size_kb']:.1f} KB")
            
            if len(scan["complete"]) > 5:
                print(f"  ... et {len(scan['complete']) - 5} autres")
        
        # Détails des manquantes
        if scan["missing"]:
            print("\n" + "-" * 70)
            print("❌ VIDÉOS MANQUANTES (à traiter)")
            print("-" * 70)
            for item in scan["missing"]:
                print(f"  ✗ {item['video'].name}")
                print(f"    → {item['info']['reason']}")
        
        # Détails des incomplètes
        if scan["incomplete"]:
            print("\n" + "-" * 70)
            print("⚠️  VIDÉOS INCOMPLÈTES (à retraiter)")
            print("-" * 70)
            for item in scan["incomplete"]:
                print(f"  ! {item['video'].name}")
                print(f"    → {item['info']['reason']}")
        
        # Détails des corrompues
        if scan["corrupted"]:
            print("\n" + "-" * 70)
            print("🔴 VIDÉOS CORROMPUES (à retraiter)")
            print("-" * 70)
            for item in scan["corrupted"]:
                print(f"  ✗ {item['video'].name}")
                print(f"    → {item['info']['reason']}")
        
        print("\n" + "=" * 70)
        
        return scan


# Point d'entrée pour vérification standalone
if __name__ == "__main__":
    validator = TrajectoryValidator()
    validator.print_scan_report()