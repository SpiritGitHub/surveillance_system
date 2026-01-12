import sys
import logging
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent))

from src.pipeline.process_video import process_video
from src.pipeline.global_matching import run_global_matching
from src.interface.dashboard_v import DashboardV
from src.utils.trajectory_validator import TrajectoryValidator

def main_v():
    print("\n" + "=" * 70)
    print("🚀 SURVEILLANCE SYSTEM - VERSION AVANCÉE (V)")
    print("=" * 70)
    
    # 1. PROCESS VIDEOS (Standard)
    # We reuse the standard processing logic
    validator = TrajectoryValidator()
    videos_to_process = validator.get_videos_to_process()
    
    if videos_to_process:
        print(f"Traitement de {len(videos_to_process)} nouvelles vidéos...")
        for video_path in videos_to_process:
            try:
                process_video(str(video_path), show_video=False)
            except Exception as e:
                print(f"Erreur sur {video_path}: {e}")
    else:
        print("Toutes les vidéos sont déjà traitées.")

    # 2. GLOBAL MATCHING (Standard)
    # Always run to ensure latest links
    run_global_matching()

    # 3. DASHBOARD V (New)
    print("\n" + "=" * 70)
    print("📺 Lancement du Dashboard V")
    print("=" * 70)
    print("Chargement de l'interface synchronisée...")
    
    try:
        dashboard = DashboardV()
        dashboard.load_resources()
        dashboard.run()
    except Exception as e:
        print(f"Erreur Dashboard: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main_v()
