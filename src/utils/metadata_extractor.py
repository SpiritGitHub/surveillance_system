"""
Script pour extraire TOUTES les métadonnées disponibles des vidéos
Utilise plusieurs méthodes pour récupérer le maximum d'informations
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
from pymediainfo import MediaInfo
import cv2


def extract_with_mediainfo(video_path: Path):
    """
    Extraction avec pymediainfo (très complet)
    """
    print(f"\n[MediaInfo] Analyse de {video_path.name}...")
    
    media_info = MediaInfo.parse(str(video_path))
    metadata = {}
    
    for track in media_info.tracks:
        track_data = {}
        
        # Récupérer tous les attributs non-privés
        for attr in dir(track):
            if not attr.startswith('_'):
                value = getattr(track, attr, None)
                if value and not callable(value):
                    track_data[attr] = str(value)
        
        if track_data:
            track_type = track.track_type
            metadata[f"{track_type}_track"] = track_data
    
    return metadata


def extract_with_ffprobe(video_path: Path):
    """
    Extraction avec ffprobe (outil ffmpeg)
    Nécessite ffmpeg installé
    """
    print(f"[FFprobe] Analyse de {video_path.name}...")
    
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"[FFprobe] ⚠️ Erreur : {result.stderr}")
            return {}
    
    except FileNotFoundError:
        print("[FFprobe] ⚠️ ffmpeg n'est pas installé")
        return {}
    except Exception as e:
        print(f"[FFprobe] ⚠️ Erreur : {e}")
        return {}


def extract_with_opencv(video_path: Path):
    """
    Extraction basique avec OpenCV
    """
    print(f"[OpenCV] Analyse de {video_path.name}...")
    
    cap = cv2.VideoCapture(str(video_path))
    
    metadata = {
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "total_frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fourcc": int(cap.get(cv2.CAP_PROP_FOURCC)),
        "format": cap.get(cv2.CAP_PROP_FORMAT),
        "mode": cap.get(cv2.CAP_PROP_MODE),
        "brightness": cap.get(cv2.CAP_PROP_BRIGHTNESS),
        "contrast": cap.get(cv2.CAP_PROP_CONTRAST),
        "saturation": cap.get(cv2.CAP_PROP_SATURATION),
        "hue": cap.get(cv2.CAP_PROP_HUE)
    }
    
    cap.release()
    return metadata


def extract_filesystem_data(video_path: Path):
    """
    Métadonnées du système de fichiers
    """
    stat = video_path.stat()
    
    return {
        "filename": video_path.name,
        "file_size_bytes": stat.st_size,
        "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
        "created_time": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "accessed_time": datetime.fromtimestamp(stat.st_atime).isoformat()
    }


def load_drive_metadata(video_path: Path):
    """
    Métadonnées Google Drive
    """
    metadata_file = Path("data/videos/videos_metadata.json")
    
    if not metadata_file.exists():
        return None
    
    with open(metadata_file, 'r') as f:
        all_metadata = json.load(f)
    
    return all_metadata.get(video_path.name)


def extract_all_metadata(video_path: str):
    """
    Extraction complète de TOUTES les métadonnées
    """
    video_path = Path(video_path)
    
    if not video_path.exists():
        print(f"[ERREUR] Fichier introuvable : {video_path}")
        return None
    
    print("=" * 70)
    print(f"📹 EXTRACTION MÉTADONNÉES : {video_path.name}")
    print("=" * 70)
    
    all_metadata = {
        "extraction_date": datetime.now().isoformat(),
        "video_path": str(video_path)
    }
    
    # 1. Système de fichiers
    print("\n[1/5] Métadonnées système de fichiers...")
    all_metadata["filesystem"] = extract_filesystem_data(video_path)
    
    # 2. OpenCV
    print("[2/5] Métadonnées OpenCV...")
    all_metadata["opencv"] = extract_with_opencv(video_path)
    
    # 3. MediaInfo (le plus complet)
    print("[3/5] Métadonnées MediaInfo...")
    try:
        all_metadata["mediainfo"] = extract_with_mediainfo(video_path)
    except Exception as e:
        print(f"[MediaInfo] ⚠️ Erreur : {e}")
        all_metadata["mediainfo"] = {}
    
    # 4. FFprobe
    print("[4/5] Métadonnées FFprobe...")
    all_metadata["ffprobe"] = extract_with_ffprobe(video_path)
    
    # 5. Google Drive
    print("[5/5] Métadonnées Google Drive...")
    drive_meta = load_drive_metadata(video_path)
    if drive_meta:
        all_metadata["google_drive"] = drive_meta
        print("  ✓ Données Drive trouvées")
    else:
        print("  ⚠️ Pas de données Drive")
    
    # Sauvegarder
    output_dir = Path("data/metadata_full")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"{video_path.stem}_full.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_metadata, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 70)
    print(f"✅ MÉTADONNÉES SAUVEGARDÉES : {output_file}")
    print("=" * 70)
    
    # Afficher un résumé
    print("\n📊 RÉSUMÉ DES MÉTADONNÉES TROUVÉES :")
    print(f"   • Système : {len(all_metadata.get('filesystem', {}))} champs")
    print(f"   • OpenCV : {len(all_metadata.get('opencv', {}))} champs")
    print(f"   • MediaInfo : {len(all_metadata.get('mediainfo', {}))} sections")
    print(f"   • FFprobe : {len(all_metadata.get('ffprobe', {}))} champs")
    print(f"   • Google Drive : {'✓' if all_metadata.get('google_drive') else '✗'}")
    
    # Rechercher les timestamps et GPS
    print("\n🔍 RECHERCHE DONNÉES TEMPORELLES ET GPS :")
    
    timestamps_found = []
    gps_found = []
    
    # Chercher dans MediaInfo
    if "mediainfo" in all_metadata:
        for section_name, section_data in all_metadata["mediainfo"].items():
            for key, value in section_data.items():
                key_lower = key.lower()
                if any(word in key_lower for word in ['date', 'time', 'recorded', 'tagged', 'encoded']):
                    timestamps_found.append(f"{section_name}.{key}: {value}")
                if any(word in key_lower for word in ['gps', 'latitude', 'longitude', 'location']):
                    gps_found.append(f"{section_name}.{key}: {value}")
    
    # Chercher dans FFprobe
    if "ffprobe" in all_metadata and "format" in all_metadata["ffprobe"]:
        tags = all_metadata["ffprobe"]["format"].get("tags", {})
        for key, value in tags.items():
            key_lower = key.lower()
            if any(word in key_lower for word in ['date', 'time', 'creation']):
                timestamps_found.append(f"FFprobe.{key}: {value}")
            if any(word in key_lower for word in ['location', 'gps']):
                gps_found.append(f"FFprobe.{key}: {value}")
    
    # Afficher résultats
    if timestamps_found:
        print("   📅 Timestamps trouvés :")
        for ts in timestamps_found[:5]:  # Limiter à 5
            print(f"      • {ts}")
    else:
        print("   ❌ Aucun timestamp trouvé dans la vidéo")
        print("      → Utiliser les dates du système de fichiers")
    
    if gps_found:
        print("   📍 GPS trouvé :")
        for gps in gps_found:
            print(f"      • {gps}")
    else:
        print("   ❌ Aucune donnée GPS trouvée")
        print("      → Utiliser la configuration manuelle des caméras")
    
    return all_metadata


def analyze_all_videos():
    """
    Analyse toutes les vidéos du dossier
    """
    video_dir = Path("data/videos")
    videos = list(video_dir.glob("*.mp4"))
    
    print(f"\n🎬 ANALYSE DE {len(videos)} VIDÉO(S)\n")
    
    results = {}
    
    for idx, video_path in enumerate(videos, 1):
        print(f"\n{'='*70}")
        print(f"VIDÉO {idx}/{len(videos)}")
        print(f"{'='*70}")
        
        try:
            metadata = extract_all_metadata(str(video_path))
            results[video_path.name] = "success"
        except Exception as e:
            print(f"[ERREUR] {video_path.name} : {e}")
            results[video_path.name] = f"error: {e}"
    
    # Résumé final
    print("\n" + "="*70)
    print("📊 RÉSUMÉ FINAL")
    print("="*70)
    success = sum(1 for v in results.values() if v == "success")
    print(f"✅ Succès : {success}/{len(videos)}")
    print(f"❌ Erreurs : {len(videos) - success}/{len(videos)}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Analyser une vidéo spécifique
        extract_all_metadata(sys.argv[1])
    else:
        # Analyser toutes les vidéos
        analyze_all_videos()