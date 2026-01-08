from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from person_database import PersonDatabase


def main():
    """Jour 21 : Construction base personnes"""
    
    print("\n🎯 JOUR 21 - BASE PERSONNES (Milestone 3)")
    print("=" * 70)
    
    # Vérifier trajectoires
    traj_dir = Path("data/trajectories")
    if not traj_dir.exists() or not list(traj_dir.glob("*.json")):
        print("❌ Aucune trajectoire trouvée !")
        print("   Lancez d'abord: python main.py")
        return
    
    # Construire la base
    db = PersonDatabase(output_file="data/personnes.csv")
    persons = db.build_database()
    
    if persons:
        print(f"\n✅ Milestone 3 atteinte !")
        print(f"📁 Fichier: data/personnes.csv")
        print(f"👥 {len(persons)} personne(s) avec ID stable dans leur vidéo")
        
        print("\n📋 Aperçu (5 premières):")
        print("-" * 70)
        for p in persons[:5]:
            print(f"  Track {p['track_id']} | {p['video_id']}")
            print(f"    → {p['frames_count']} frames | Frames {p['first_seen']}-{p['last_seen']}")
        
        print("\n🎯 Prochaine étape: SEMAINE 4 - Zones interdites")
    else:
        print("\n⚠️  Aucune personne extraite")


if __name__ == "__main__":
    main()