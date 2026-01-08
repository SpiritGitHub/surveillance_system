import os
import json
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed
from tqdm import tqdm

from auth import authenticate

# CONFIGURATION
DOWNLOAD_DIR = "data/videos"
METADATA_FILE = "data/videos/videos_metadata.json"
FOLDER_ID = "16yA8Dnp9W6_MDq4ydE5ad-VF5zAlHMng"

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv")

# UTILS
def load_metadata():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_metadata(metadata):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)


# DOWNLOAD video FILE avec barre de progression
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def download_file(service, file_id, filename, save_path, file_size):
    request = service.files().get_media(fileId=file_id)

    with open(save_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        
        # Créer une barre de progression
        with tqdm(
            total=file_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            desc=f"📥 {filename}",
            ncols=100,
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        ) as pbar:
            previous_bytes = 0
            
            while not done:
                status, done = downloader.next_chunk()
                
                if status:
                    current_bytes = int(status.resumable_progress)
                    # Mettre à jour seulement les nouveaux octets téléchargés
                    pbar.update(current_bytes - previous_bytes)
                    previous_bytes = current_bytes

# MAIN SYNC FUNCTION
def sync_drive_videos():
    logger.info("🚀 Démarrage synchronisation Google Drive")

    creds = authenticate()
    service = build("drive", "v3", credentials=creds)

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    metadata = load_metadata()

    query = f"'{FOLDER_ID}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name, size, mimeType, createdTime, modifiedTime)"
    ).execute()

    files = results.get("files", [])

    if not files:
        logger.warning("⚠️  Aucune vidéo trouvée sur Drive")
        return

    # Filtrer uniquement les vidéos
    video_files = [f for f in files if f["name"].lower().endswith(VIDEO_EXTENSIONS)]
    
    # CORRECTION : Utiliser print() au lieu de logger.info() avec f-string
    print(f"📊 {len(video_files)} vidéo(s) trouvée(s) sur Drive")
    
    # Compter les vidéos à télécharger
    to_download = [f for f in video_files if f["name"] not in metadata]
    
    if not to_download:
        logger.success("✅ Toutes les vidéos sont déjà téléchargées")
        return
    
    # CORRECTION : Utiliser print() au lieu de logger.info() avec f-string
    print(f"⬇️  {len(to_download)} vidéo(s) à télécharger")
    print()  # Ligne vide pour la lisibilité

    for idx, file in enumerate(to_download, 1):
        name = file["name"]
        local_path = os.path.join(DOWNLOAD_DIR, name)
        file_size = int(file.get("size", 0))

        try:
            print(f"\n[{idx}/{len(to_download)}] Téléchargement en cours...")
            download_file(service, file["id"], name, local_path, file_size)

            # Vérification fichier corrompu
            if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                raise ValueError("Fichier corrompu ou vide")

            # Enregistrement metadata
            metadata[name] = {
                "file_id": file["id"],
                "local_path": local_path,
                "size_bytes": file_size,
                "mime_type": file.get("mimeType"),
                "created_time": file.get("createdTime"),
                "modified_time": file.get("modifiedTime"),
                "downloaded_at": datetime.utcnow().isoformat(),
                "status": "downloaded"
            }

            save_metadata(metadata)
            logger.success(f"✅ Téléchargement réussi : {name}")

        except Exception as e:
            # CORRECTION : Utiliser print() au lieu de logger.error() avec f-string
            print(f"❌ Erreur sur {name} : {e}")

            if os.path.exists(local_path):
                os.remove(local_path)
    
    print()  # Ligne vide finale
    print(f"🎉 Synchronisation terminée ! {len(to_download)} vidéo(s) téléchargée(s)")


if __name__ == "__main__":
    sync_drive_videos()