# Surveillance System — Détection, tracking et analyse multi‑caméras

Pipeline Python pour transformer des vidéos multi‑caméras en données structurées (trajectoires, identités globales, événements) afin de faciliter l'analyse et l'audit : qui est passé où, quand, et pendant combien de temps.

Ce README vise un usage “GitHub‑friendly” : clonage, installation, configuration locale (données/credentials), lancement, sorties, et règles de confidentialité.

## Sommaire

- Fonctionnalités
- Ce qui est versionné / ignoré
- Quickstart (Windows)
- Prérequis
- Installation
- Données & configuration locale
- Exécution
- Sorties
- Notebooks
- Dépannage
- Sécurité & confidentialité

## Fonctionnalités

- Détection multi‑classes (YOLOv8) : personnes, véhicules, bagages
- Tracking par classe (DeepSORT) et export des trajectoires
- Zones interdites (polygones) + événements d'intrusion (immédiat ou seuil de durée)
- Ré‑identification multi‑cam (Re‑ID) pour `person` → `global_id`
- Synchronisation multi‑cam par offsets → timeline commune `t_sync`
- Enrichissement (prev/next camera) + déduplication (zones recouvrantes)
- Exports “database” (CSV) + rapport de run (JSON)

## Ce qui est versionné / ignoré

Le dépôt est conçu pour garder le code sur GitHub tout en évitant de pousser des données lourdes ou sensibles.

- Versionné : code (`src/`, `main.py`, `main_v.py`), `requirements.txt`, `README.md`
- Ignoré par Git (`.gitignore`) :
  - `data/` (vidéos, frames, trajectoires, embeddings, zones, metadata…)
  - `outputs/` (events, reports, logs…)
  - `configs/` (fichiers de config + credentials OAuth)
  - `doc/` (documentation interne locale)
  - `oauth.txt`, `.env`, logs, caches…

Conséquence : après clonage, tu dois recréer/peupler `data/` et `configs/` en local.

## Quickstart (Windows)

1) Cloner

```powershell
git clone https://github.com/SpiritGitHub/surveillance_system.git
cd surveillance_system
```

Alternative (SSH) :

```powershell
git clone git@github.com:SpiritGitHub/surveillance_system.git
cd surveillance_system
```

Mettre à jour le code :

```powershell
git pull
```

2) Créer/activer un venv

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

3) Installer les dépendances

```powershell
pip install -r requirements.txt
```

4) Préparer l'arborescence locale (minimum)

```powershell
mkdir data\videos
mkdir data\trajectories
mkdir outputs\events
mkdir outputs\reports
mkdir configs
```

5) Ajouter des vidéos `*.mp4` dans `data\videos\`, puis lancer

```powershell
python main.py
```

## Prérequis

- OS : Windows 10/11 (fonctionne généralement sous Linux, mais usage principal sous Windows)
- Python : 3.10+ (recommandé : 3.11)
- Accès aux vidéos `*.mp4`

### Accélération (optionnel)

- GPU NVIDIA : recommandé pour accélérer YOLO/ReID (PyTorch CUDA)
- CPU only : fonctionne, mais plus lent

Note : `requirements.txt` contient des versions PyTorch CUDA (`+cu121`). Sur une machine sans CUDA, adapte l'installation (voir section suivante).

## Installation

### 1) Environnement virtuel

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

### 2) Dépendances

Option A — machine avec CUDA (si compatible) :

```powershell
pip install -r requirements.txt
```

Option B — machine CPU only :

1) Installer PyTorch CPU :

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

2) Installer le reste :

```powershell
pip install -r requirements.txt
```

Si pip refuse à cause des wheels `+cu121`, remplace/supprime les lignes `torch/torchvision/torchaudio` dans `requirements.txt` et installe PyTorch séparément (comme ci‑dessus).

## Données & configuration locale

Comme `data/` et `configs/` sont ignorés par Git, voici l'arborescence minimale attendue en local :

```text
data/
	videos/                          # fichiers .mp4
	trajectories/                    # généré par le pipeline
	embeddings/                      # généré par le pipeline
	camera_offsets_timestamp.json    # optionnel (préféré)
	camera_offsets_durree.json       # optionnel (fallback)
	zones_interdites.json            # recommandé (zones d'intrusion)
	video_orientations.json          # optionnel (rotation par caméra)

configs/
	cameras.json                     # optionnel selon usages
	camera_network.json              # optionnel (topologie/gating)
	credentials.json                 # optionnel (Google Drive)
	token.json                       # généré par OAuth
```

### Modèles

Le dépôt contient déjà des poids YOLO dans `models/yolo/` (ex : `yolov8n.pt`). Les éléments Re‑ID sont sous `models/reid/`.

### Réseau de caméras (topologie / gating) — optionnel

Le “gating” topologique sert à empêcher des associations Re‑ID impossibles (caméras non atteignables).

- Fichier (local) : `configs/camera_network.json`
- Format des arêtes :
  - Sans temps : `{ "from": "CAMERA_A", "to": "CAMERA_B" }`
  - Avec temps : `{ "from": "CAMERA_A", "to": "CAMERA_B", "min_s": 3, "max_s": 120 }`

Si tu ne veux pas de gating, mets `"edges": []`.

### Zones interdites (intrusions)

Pour définir les zones, utilise l'outil visuel :

```powershell
python src/zones/zone_visual.py
```

Le fichier de sortie est généralement `data/zones_interdites.json`.

Astuce (anti‑doublons) : si deux caméras couvrent la même zone physique, utilise le même `name` pour faciliter la déduplication.

## Exécution

### Pipeline complet (traitement + matching + exports)

```powershell
python main.py
```

Options utiles :

- Retraiter toutes les vidéos :

```powershell
python main.py --force
```

Important : même si aucune vidéo n'est à retraiter, `main.py` exécute la fin de chaîne (matching global, enrichissement, rapport, exports) tant que `data/trajectories/` existe.

### Version “V” (pipeline + dashboard)

```powershell
python main_v.py
```

Exemples :

- Retraitement complet + dashboard : `python main_v.py --force`
- Pipeline only (sans UI) : `python main_v.py --no-dashboard`
- Dashboard only (sans retraitement) : `python main_v.py --dashboard-only`
- Offsets pour la synchro du dashboard :
  - `--offset-source trajectory` (défaut)
  - `--offset-source timestamp` (lit `data/camera_offsets_timestamp.json`)
  - `--offset-source duration` (lit `data/camera_offsets_durree.json`)
  - `--offset-source none`
  - `--offset-source custom --offset-file path\\to\\offsets.json`

## Sorties

- Trajectoires : `data/trajectories/*.json` (inclut `t_sync` + embeddings Re‑ID)
- Embeddings exportés : `data/embeddings/<VIDEO_ID>/*.npy` + `data/embeddings/embeddings_index_<RUN_ID>.csv`
- Événements : `outputs/events/events_<RUN_ID>.jsonl`
- Rapport : `outputs/reports/run_report_<RUN_ID>.json` + `outputs/reports/latest.json`
- Exports CSV :
  - `database/personnes.csv`
  - `database/evenements.csv`
  - `database/classes.csv`

### Fichiers vides : cas fréquents

- `outputs/events/...` et `database/evenements.csv` peuvent être vides si aucune intrusion n'est détectée (zones absentes/inactives, seuil `min_duration` trop élevé, aucune personne dans une zone…).
- `database/classes.csv` est généré à partir des trajectoires (même si 0 vidéo retraitée).

## Notebooks

Les notebooks dans `notebooks/` servent à inspecter/valider les exports CSV (personnes, événements, classes, vidéos).

## Dépannage

- Erreur d'installation PyTorch / CUDA : utilise l'installation CPU (section “Installation”), ou aligne les versions CUDA/PyTorch avec ton poste.
- “Aucune vidéo retraitée” : vérifie `data/videos/` et/ou utilise `--force`.
- Pas d'événements : vérifie que `data/zones_interdites.json` existe et que les seuils/zones sont cohérents.

## Sécurité & confidentialité

Ce projet traite des vidéos potentiellement sensibles.

- Ne versionne pas les vidéos/frames/trajectoires/embeddings sur GitHub.
- Ne versionne pas `configs/credentials.json` et `configs/token.json`.
- Si tu automatises (CI), utilise des secrets et des chemins locaux/volumes dédiés.

