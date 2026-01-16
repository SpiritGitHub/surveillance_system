# Surveillance System — Détection, tracking et analyse multi‑caméras

Pipeline Python pour transformer des vidéos multi‑caméras en **données structurées** (trajectoires, identités globales, événements) afin de faciliter l’analyse et l’audit : **qui est passé où, quand, et pendant combien de temps**.

Ce dépôt est pensé pour un usage “projet” : installation, exécution batch, visualisation (dashboard), artefacts inspectables (JSON/CSV), et bonnes pratiques de confidentialité.

## Sommaire

- Aperçu
- Fonctionnalités
- Structure du projet
- Ce qui est versionné / ignoré (Git)
- Installation (Windows)
- Configuration & données attendues
- Exécution
- Sorties (artefacts)
- Notebooks
- Dépannage
- Sécurité & confidentialité

## Aperçu

- **Entrée** : vidéos `.mp4` (une par caméra) dans `data/videos/`
- **Traitement** : YOLO (détection) → DeepSORT (tracking) → zones (intrusions) → ReID (person) → synchronisation multi‑cam (`t_sync`)
- **Sortie** : `data/trajectories/*.json`, événements JSONL, rapport de run, exports CSV dans `database/`

## Fonctionnalités

- Détection multi‑classes (YOLOv8)
- Tracking **par classe** (DeepSORT) + export trajectoires JSON
- Zones interdites (polygones) + événements d’intrusion (`intrusion_confirmed` / `intrusion_ended`)
- Ré‑identification multi‑cam (Re‑ID) pour la classe `person` → `global_id`
- Synchronisation multi‑cam via offsets → timeline commune `t_sync = t + offset`
- Enrichissement d’événements (`global_id`, `prev_camera`, `next_camera`)
- Export embeddings (fichiers `.npy` + index CSV)
- Exports “database” (CSV) + rapport de run (JSON)

## Structure du projet

Arborescence (vue simplifiée) :

```text
.
├─ main.py                     # Pipeline batch end-to-end
├─ main_v.py                   # Pipeline + dashboard synchronisé
├─ requirements.txt            # Dépendances Python
├─ configs/                    # Configs locales (souvent non versionnées)
├─ data/                       # Données locales (vidéos + artefacts)
├─ database/                   # Exports CSV “tables”
├─ doc/                        # Documentation (guide technique, etc.)
├─ models/                     # Poids YOLO + composants ReID
├─ notebooks/                  # Notebooks d’analyse des CSV
├─ outputs/                    # Événements, logs, rapports, screenshots
└─ src/
   ├─ alerts/                  # Gestion d’alertes/intrusions
   ├─ database/                # Export CSV
   ├─ detection/               # YOLO wrapper
   ├─ drive/                   # Sync Google Drive (optionnel)
   ├─ interface/               # Dashboard V
   ├─ metadata/                # Metadata vidéos
   ├─ pipeline/                # Orchestration vidéo + matching global
   ├─ reid/                    # Extraction embeddings + matching
   ├─ tracking/                # DeepSORT wrapper
   ├─ utils/                   # Outils (logs, rapport, enrichissement, validation)
   └─ zones/                   # Zones interdites + outils visuels
```

Pour une description détaillée dossier par dossier (APIs, formats), voir : `doc/TECHNICAL_GUIDE.md`.

## Ce qui est versionné / ignoré (Git)

Le dépôt évite de pousser des données lourdes/sensibles (vidéos, configs OAuth, caches). La source d’autorité est `.gitignore`.

Actuellement, `.gitignore` ignore notamment :

- `venv/`, `__pycache__/`, caches notebooks
- `configs/` (souvent sensible : credentials OAuth, tokens, configs locales)
- `oauth.txt`, `.env`, `*.log`
- `data/videos/`, `data/trajectories/`, `data/frames/`
- `doc/PRESENTATION.md`

Conséquence : après clonage, tu devras (re)créer et peupler au minimum `data/videos/` et tes fichiers `configs/`.

## Installation (Windows)

### 1) Cloner

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

### 2) Créer/activer un venv

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3) Installer les dépendances

```powershell
pip install -r requirements.txt
```

### 4) Préparer l'arborescence locale (minimum)

```powershell
mkdir data\videos
mkdir data\trajectories
mkdir outputs\events
mkdir outputs\reports
mkdir configs
```

### 5) Ajouter des vidéos dans `data\videos\`, puis lancer

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

Note : `requirements.txt` contient des wheels PyTorch CUDA (`+cu121`). Sur une machine sans CUDA, adapte l’installation (voir ci‑dessous).

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

Si `pip` refuse à cause des wheels `+cu121`, installe PyTorch séparément (CPU), puis installe le reste (ou supprime temporairement les lignes `torch*` du fichier).

## Configuration & données attendues

### Arborescence locale minimale

Comme certaines données/configs sont ignorées par Git, voici l’arborescence minimale attendue en local :

```text
data/
  videos/                          # fichiers .mp4 (entrée)
  trajectories/                    # généré (trajectoires JSON)
  embeddings/                      # généré (embeddings .npy + index CSV)
  camera_offsets_timestamp.json    # optionnel (préféré)
  camera_offsets_durree.json       # optionnel (fallback)
  zones_interdites.json            # recommandé (zones d’intrusion)
  video_orientations.json          # généré/optionnel (rotation par caméra)

configs/
  camera_network.json              # optionnel (topologie/gating)
  credentials.json                 # optionnel (Google Drive)
  token.json                       # généré par OAuth
```

### Identifiants et conventions

- `video_id` = nom de fichier sans extension (ex: `CAMERA_HALL_PORTE_ENTREE` pour `CAMERA_HALL_PORTE_ENTREE.mp4`).
- Les trajectoires sont écrites dans `data/trajectories/<video_id>.json`.

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

Important : même si aucune vidéo n’est à retraiter, `main.py` exécute la fin de chaîne (matching global, enrichissement, rapport, exports) tant que `data/trajectories/` contient des JSON.

### Version “V” (pipeline + dashboard)

```powershell
python main_v.py
```

Exemples :

- Retraitement complet + dashboard : `python main_v.py --force`
- Pipeline only (sans UI) : `python main_v.py --no-dashboard`
- Dashboard only (sans retraitement) : `python main_v.py --dashboard-only`
- Offsets pour la synchro du dashboard :
  - `--offset-source timestamp` (défaut, lit `data/camera_offsets_timestamp.json`)
  - `--offset-source trajectory` (utilise `sync_offset` des trajectoires)
  - `--offset-source duration` (lit `data/camera_offsets_durree.json`)
  - `--offset-source none`
  - `--offset-source custom --offset-file path\\to\\offsets.json`

## Sorties (artefacts)

- Trajectoires : `data/trajectories/*.json` (inclut `t_sync` + embeddings Re‑ID)
- Embeddings exportés : `data/embeddings/<VIDEO_ID>/*.npy` + `data/embeddings/embeddings_index_<RUN_ID>.csv`
- Événements : `outputs/events/events_<RUN_ID>.jsonl`
- Rapport : `outputs/reports/run_report_<RUN_ID>.json` + `outputs/reports/latest.json`
- Exports CSV :
  - `database/personnes.csv`
  - `database/evenements.csv`
  - `database/classes.csv`
  - `database/videos.csv` (si export activé)

### Fichiers vides : cas fréquents

- `outputs/events/...` et `database/evenements.csv` peuvent être vides si aucune intrusion n'est détectée (zones absentes/inactives, seuil `min_duration` trop élevé, aucune personne dans une zone…).
- `database/classes.csv` est généré à partir des trajectoires (même si 0 vidéo retraitée).

## Notebooks

Les notebooks dans `notebooks/` servent à inspecter/valider les exports CSV (personnes, événements, classes, vidéos).

## Dépannage

- Erreur d’installation PyTorch / CUDA : utilise l’installation CPU (section “Installation”), ou aligne CUDA/PyTorch avec ton poste.
- “Aucune vidéo retraitée” : vérifie `data/videos/` et/ou utilise `--force`.
- Pas d’événements : vérifie que `data/zones_interdites.json` existe, que `active=true`, et que la zone couvre réellement la scène (orientation comprise).

## Sécurité & confidentialité

Ce projet traite des vidéos potentiellement sensibles.

- Ne versionne pas des données sensibles (vidéos, frames, trajectoires, embeddings).
- Ne versionne pas `configs/credentials.json` et `configs/token.json`.
- Pour toute automatisation (CI), utilise des secrets et des volumes dédiés.


