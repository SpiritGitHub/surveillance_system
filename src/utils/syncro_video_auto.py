"""
Outil de synchronisation automatique des vidéos basé sur les métadonnées
Calcule les offsets en utilisant les timestamps de création ou la durée des vidéos
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class AutoVideoSyncTool:
    """Outil pour synchroniser automatiquement les vidéos via métadonnées"""
    
    def __init__(self):
        self.metadata_dir = Path("data/metadata_full")
        self.offsets = {}
        self.offsets_file = Path("data/camera_offsets.json")
        self.video_metadata = {}
    
    def load_metadata(self):
        """Charge toutes les métadonnées des vidéos"""
        if not self.metadata_dir.exists():
            print(f"ERREUR: dossier de métadonnées introuvable: {self.metadata_dir}")
            return False
        
        metadata_files = list(self.metadata_dir.glob("*.json"))
        
        if not metadata_files:
            print(f"ERREUR: aucun fichier de métadonnées trouvé dans {self.metadata_dir}")
            return False
        
        print("\nChargement des métadonnées...")
        
        for meta_file in metadata_files:
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                camera_id = meta_file.stem
                self.video_metadata[camera_id] = data
                print(f"   - {camera_id}")
                
            except Exception as e:
                print(f"   ERREUR lecture {meta_file.name}: {e}")
        
        print(f"\nOK: {len(self.video_metadata)} métadonnée(s) chargée(s)")
        return len(self.video_metadata) > 0
    
    def extract_timestamps(self, camera_id: str) -> Dict[str, Optional[datetime]]:
        """Extrait tous les timestamps disponibles pour une caméra"""
        metadata = self.video_metadata.get(camera_id, {})
        timestamps = {}
        
        # 1. Google Drive - created_time
        if 'google_drive' in metadata and 'created_time' in metadata['google_drive']:
            try:
                ts_str = metadata['google_drive']['created_time']
                # Format: "2025-12-11T13:25:50.459Z"
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                timestamps['gdrive_created'] = ts
            except:
                pass
        
        # 2. Google Drive - modified_time
        if 'google_drive' in metadata and 'modified_time' in metadata['google_drive']:
            try:
                ts_str = metadata['google_drive']['modified_time']
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                timestamps['gdrive_modified'] = ts
            except:
                pass
        
        # 3. MediaInfo - encoded_date (Video track)
        if 'mediainfo' in metadata and 'Video_track' in metadata['mediainfo']:
            video_track = metadata['mediainfo']['Video_track']
            if 'encoded_date' in video_track:
                try:
                    ts_str = video_track['encoded_date']
                    # Format: "2025-12-11 12:21:30 UTC"
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S %Z")
                    timestamps['encoded'] = ts
                except:
                    pass
        
        # 4. Filesystem - created_time
        if 'filesystem' in metadata and 'created_time' in metadata['filesystem']:
            try:
                ts_str = metadata['filesystem']['created_time']
                ts = datetime.fromisoformat(ts_str)
                timestamps['fs_created'] = ts
            except:
                pass
        
        # 5. Filesystem - modified_time
        if 'filesystem' in metadata and 'modified_time' in metadata['filesystem']:
            try:
                ts_str = metadata['filesystem']['modified_time']
                ts = datetime.fromisoformat(ts_str)
                timestamps['fs_modified'] = ts
            except:
                pass
        
        return timestamps
    
    def get_duration(self, camera_id: str) -> Optional[float]:
        """Récupère la durée de la vidéo en secondes"""
        metadata = self.video_metadata.get(camera_id, {})
        
        # Essayer OpenCV
        if 'opencv' in metadata:
            fps = metadata['opencv'].get('fps')
            total_frames = metadata['opencv'].get('total_frames')
            if fps and total_frames:
                return total_frames / fps
        
        # Essayer MediaInfo
        if 'mediainfo' in metadata and 'General_track' in metadata['mediainfo']:
            duration_ms = metadata['mediainfo']['General_track'].get('duration')
            if duration_ms:
                return float(duration_ms) / 1000.0
        
        return None
    
    def sync_by_timestamps(self) -> bool:
        """Synchronisation basée sur les timestamps de création/encodage"""
        print("\n" + "="*70)
        print("MÉTHODE 1: synchronisation par timestamps")
        print("="*70)
        
        # Collecter les timestamps pour chaque caméra
        camera_timestamps = {}
        
        for camera_id in self.video_metadata.keys():
            timestamps = self.extract_timestamps(camera_id)
            
            if not timestamps:
                print(f"AVERTISSEMENT: {camera_id}: aucun timestamp trouvé")
                continue
            
            camera_timestamps[camera_id] = timestamps
        
        if len(camera_timestamps) < 2:
            print("\nERREUR: pas assez de timestamps disponibles pour la synchronisation")
            return False
        
        # Afficher les timestamps disponibles
        print("\nTimestamps disponibles:")
        for camera_id, timestamps in camera_timestamps.items():
            print(f"\n   {camera_id}:")
            for ts_type, ts in sorted(timestamps.items()):
                print(f"      - {ts_type:20s}: {ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        
        # Demander quel type de timestamp utiliser
        print("\nQuel timestamp voulez-vous utiliser pour la synchronisation ?")
        
        # Trouver les types de timestamps communs
        all_types = set()
        for timestamps in camera_timestamps.values():
            all_types.update(timestamps.keys())
        
        common_types = all_types.copy()
        for timestamps in camera_timestamps.values():
            common_types &= set(timestamps.keys())
        
        if common_types:
            print(f"\n   Timestamps disponibles pour TOUTES les caméras:")
            for i, ts_type in enumerate(sorted(common_types), 1):
                print(f"      [{i}] {ts_type}")
        
        print(f"\n   Tous les timestamps disponibles:")
        for i, ts_type in enumerate(sorted(all_types), 1):
            marker = "OK" if ts_type in common_types else "PARTIEL"
            print(f"      [{i}] ({marker}) {ts_type}")
        
        choice = input("\n   Numéro du timestamp à utiliser [1]: ").strip()
        idx = int(choice) - 1 if choice else 0
        
        selected_type = sorted(all_types)[idx]
        print(f"\nOK: utilisation de: {selected_type}")
        
        # Collecter les timestamps sélectionnés
        selected_timestamps = {}
        for camera_id, timestamps in camera_timestamps.items():
            if selected_type in timestamps:
                selected_timestamps[camera_id] = timestamps[selected_type]
            else:
                print(f"AVERTISSEMENT: {camera_id}: timestamp '{selected_type}' non disponible, caméra ignorée")
        
        if len(selected_timestamps) < 2:
            print("\nERREUR: pas assez de caméras avec ce timestamp")
            return False
        
        # Trouver le timestamp de référence (le plus ancien = vidéo qui a commencé en premier)
        ref_camera = min(selected_timestamps.items(), key=lambda x: x[1])
        ref_camera_id, ref_timestamp = ref_camera
        
        print(f"\nCaméra de référence (vidéo la plus ancienne): {ref_camera_id}")
        print(f"   Timestamp: {ref_timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        
        # Calculer les offsets
        print("\nCalcul des offsets...")
        self.offsets = {}
        
        for camera_id, timestamp in sorted(selected_timestamps.items()):
            # Offset = différence en secondes entre cette caméra et la référence
            # Si positive: cette caméra a commencé APRÈS la référence (elle est en retard)
            # Si négative: cette caméra a commencé AVANT la référence (elle est en avance)
            offset = (timestamp - ref_timestamp).total_seconds()
            self.offsets[camera_id] = offset
            
            status = "RÉFÉRENCE" if camera_id == ref_camera_id else f"{offset:+.2f}s"
            print(f"   {camera_id:40s} {status}")
        
        return True
    
    def sync_by_duration(self) -> bool:
        """Synchronisation basée sur la durée des vidéos"""
        print("\n" + "="*70)
        print("MÉTHODE 2: synchronisation par durée")
        print("="*70)
        print("\nHypothèse: la vidéo la plus longue a commencé en premier")
        
        # Collecter les durées
        camera_durations = {}
        
        for camera_id in self.video_metadata.keys():
            duration = self.get_duration(camera_id)
            
            if duration is None:
                print(f"AVERTISSEMENT: {camera_id}: durée non disponible")
                continue
            
            camera_durations[camera_id] = duration
        
        if len(camera_durations) < 2:
            print("\nERREUR: pas assez de durées disponibles pour la synchronisation")
            return False
        
        # Afficher les durées
        print("\nDurées des vidéos:")
        for camera_id, duration in sorted(camera_durations.items(), key=lambda x: -x[1]):
            minutes = int(duration // 60)
            seconds = duration % 60
            print(f"   {camera_id:40s} {minutes:2d}m {seconds:05.2f}s ({duration:.2f}s)")
        
        # Trouver la vidéo la plus longue (référence)
        ref_camera_id = max(camera_durations.items(), key=lambda x: x[1])[0]
        ref_duration = camera_durations[ref_camera_id]
        
        print(f"\nCaméra de référence (vidéo la plus longue): {ref_camera_id}")
        print(f"   Durée: {int(ref_duration//60)}m {ref_duration%60:.2f}s")
        
        # Calculer les offsets
        print("\nCalcul des offsets...")
        self.offsets = {}
        
        for camera_id, duration in sorted(camera_durations.items()):
            # Offset = différence de durée
            # Si la vidéo est plus courte, elle a commencé plus tard (offset positif)
            offset = ref_duration - duration
            self.offsets[camera_id] = offset
            
            status = "RÉFÉRENCE" if camera_id == ref_camera_id else f"+{offset:.2f}s"
            print(f"   {camera_id:40s} {status}")
        
        print("\nAVERTISSEMENT: cette méthode suppose que toutes les vidéos se sont")
        print("   terminées au même moment. Vérifiez manuellement si nécessaire.")
        
        return True
    
    def save_offsets(self):
        """Sauvegarde les offsets"""
        self.offsets_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.offsets_file, 'w', encoding='utf-8') as f:
            json.dump(self.offsets, f, indent=2, ensure_ascii=False)
        print(f"\nOffsets sauvegardés: {self.offsets_file}")
    
    def load_existing_offsets(self):
        """Charge les offsets existants"""
        if self.offsets_file.exists():
            with open(self.offsets_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}


def main():
    """Point d'entrée"""
    print("\n" + "=" * 70)
    print("SYNCHRONISATION AUTOMATIQUE DES VIDÉOS")
    print("=" * 70)
    print("\nCet outil calcule automatiquement les offsets entre caméras")
    print("en utilisant les métadonnées des vidéos.")
    print("=" * 70)
    
    tool = AutoVideoSyncTool()
    
    # Charger les métadonnées
    if not tool.load_metadata():
        print("\nERREUR: impossible de continuer sans métadonnées")
        return
    
    # Afficher les offsets existants si présents
    existing_offsets = tool.load_existing_offsets()
    if existing_offsets:
        print("\nOffsets existants:")
        for camera_id, offset in sorted(existing_offsets.items()):
            print(f"   {camera_id:40s} {offset:+.2f}s")
        
        replace = input("\nÉcraser les offsets existants ? (o/n) [n]: ").strip().lower()
        if replace != 'o':
            print("\nOpération annulée")
            return
    
    # Choisir la méthode
    print("\n" + "=" * 70)
    print("CHOISIR LA MÉTHODE DE SYNCHRONISATION")
    print("=" * 70)
    print("\n   [1] Par timestamps (date/heure de création/encodage)")
    print("       - Plus précis si les timestamps sont fiables")
    print("       - Utilise les métadonnées de Google Drive ou MediaInfo")
    print("\n   [2] Par durée des vidéos")
    print("       - Suppose que la vidéo la plus longue a démarré en premier")
    print("       - Moins précis mais fonctionne sans timestamps")
    
    choice = input("\n   Méthode [1]: ").strip()
    
    success = False
    
    if choice == '2':
        success = tool.sync_by_duration()
    else:
        success = tool.sync_by_timestamps()
    
    if not success:
        print("\nERREUR: synchronisation échouée")
        return
    
    # Demander confirmation
    print("\n" + "=" * 70)
    print("RÉSUMÉ DES OFFSETS CALCULÉS")
    print("=" * 70)
    
    for camera_id, offset in sorted(tool.offsets.items()):
        if offset == 0:
            status = "RÉFÉRENCE (0s)"
        elif offset > 0:
            status = f"+{offset:.2f}s (démarre {offset:.2f}s APRÈS la référence)"
        else:
            status = f"{offset:.2f}s (démarre {-offset:.2f}s AVANT la référence)"
        
        print(f"   {camera_id:40s} {status}")
    
    confirm = input("\nSauvegarder ces offsets ? (o/n) [o]: ").strip().lower()
    
    if confirm != 'n':
        tool.save_offsets()
        print("\nOK: synchronisation automatique terminée")
        print("\nVous pouvez maintenant:")
        print("   - Vérifier les offsets avec l'outil de visualisation multi-caméras")
        print("   - Affiner manuellement si nécessaire avec sync_videos.py")
    else:
        print("\nOffsets non sauvegardés")


if __name__ == "__main__":
    main()