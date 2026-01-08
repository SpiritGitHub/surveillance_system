'''
Docstring for main
'''
from pathlib import Path
import time
import logging
import sys

# Désactiver les logs externes
logging.basicConfig(level=logging.CRITICAL)

from src.pipeline.process_video import process_video
from src.utils.trajectory_validator import TrajectoryValidator


def main(force_reprocess=False):
    """
    Traitement intelligent de toutes les vidéos
    
    Args:
        force_reprocess: Forcer le retraitement même si déjà fait
    """
    from tqdm import tqdm
    
    # 1. VÉRIFICATION PRÉALABLE
    validator = TrajectoryValidator()
    
    print("\n🔍 Vérification des trajectoires existantes...")
    scan = validator.print_scan_report()
    
    # 2. DÉTERMINER QUOI TRAITER
    if force_reprocess:
        print("\n⚠️  MODE FORCE: Toutes les vidéos seront retraitées")
        videos_to_process = list(Path("data/videos").glob("*.mp4"))
    else:
        videos_to_process = validator.get_videos_to_process()
    
    if not videos_to_process:
        print("\n" + "=" * 70)
        print("🎉 TOUT EST À JOUR !")
        print("=" * 70)
        print("Toutes les vidéos ont déjà été traitées.")
        print("Utilisez --force pour retraiter quand même.")
        print("=" * 70)
        return
    
    print("\n" + "=" * 70)
    print(f"🎬 {len(videos_to_process)} vidéo(s) à traiter")
    print("=" * 70)
    
    # 3. CONFIRMATION
    if not force_reprocess and len(videos_to_process) < scan["summary"]["total"]:
        print(f"\nℹ️  {scan['summary']['complete']} vidéo(s) déjà traitée(s) seront ignorées")
        response = input("\n▶️  Continuer ? (o/n) [o]: ").lower()
        if response and response not in ['o', 'oui', 'y', 'yes']:
            print("Annulé.")
            return
    
    print()
    
    # 4. TRAITEMENT
    success = 0
    errors = 0
    total_time = 0
    
    for video_path in tqdm(videos_to_process, desc="Traitement global", unit="vidéo", ncols=100):
        print(f"\n{'='*70}")
        print(f"📹 {video_path.name}")
        print('='*70)
        
        start = time.time()
        
        try:
            stats = process_video(
                str(video_path),
                show_video=False
            )
            
            elapsed = time.time() - start
            total_time += elapsed
            
            if stats:
                print(f"\n✓ Succès en {elapsed:.1f}s - {stats['unique_persons']} personne(s)")
                success += 1
            
        except KeyboardInterrupt:
            print("\n⏸️  Interruption utilisateur")
            break
        except Exception as e:
            print(f"\n❌ Erreur: {str(e)[:200]}")
            errors += 1
    
    # 5. RÉSUMÉ FINAL
    print("\n" + "=" * 70)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 70)
    print(f"✅ Succès: {success}/{len(videos_to_process)}")
    print(f"❌ Erreurs: {errors}/{len(videos_to_process)}")
    print(f"⏱️  Temps total: {total_time/60:.1f} min")
    if success > 0:
        print(f"⚡ Temps moyen: {total_time/success:.1f}s par vidéo")
    print(f"📁 Trajectoires: data/trajectories/")
    print("=" * 70)
    
    # 6. VÉRIFICATION FINALE
    if success > 0:
        print("\n🔍 Vérification finale...")
        final_scan = validator.scan_all_videos()
        print(f"✅ {final_scan['summary']['complete']}/{final_scan['summary']['total']} vidéos complètes")


if __name__ == "__main__":
    # Vérifier les arguments
    force = "--force" in sys.argv or "-f" in sys.argv
    
    try:
        main(force_reprocess=force)
    except KeyboardInterrupt:
        print("\n\n⏹️  Arrêt demandé")