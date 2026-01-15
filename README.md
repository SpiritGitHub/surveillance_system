# Surveillance System — Détection, tracking et analyse multi-caméras

Ce projet transforme des vidéos multi-caméras en données structurées (trajectoires, identités globales, événements) pour faciliter l'analyse et l'audit (qui est passé où, quand, et pendant combien de temps).

L'objectif de ce README est d'être “GitHub-friendly” : installation, lancement, structure attendue, et surtout ce qui n'est pas versionné (données/credentials/sorties).

## Fonctionnalités (résumé)

- Détection multi-classes (YOLOv8) : personnes, véhicules, bagages
- Tracking par classe (DeepSORT) et export des trajectoires
- Zones interdites (polygones) + événements d'intrusion (seuil de durée ou immédiat)
- Ré-identification multi-cam (Re-ID) pour `person` → `global_id`
- Synchronisation multi-cam par offsets → timeline commune `t_sync`
- Enrichissement des événements (prev/next camera) + déduplication (zones recouvrantes)
- Exports “database” (CSV) + rapport de run (JSON)

## Ce qui est versionné / ignoré (important pour GitHub)

Le dépôt est conçu pour garder le code sur GitHub tout en évitant de pousser des données lourdes/sensibles.

- Versionné : code (`src/`, `main.py`, `main_v.py`), `requirements.txt`, ce `README.md`
- Ignoré par Git (`.gitignore`) :
	- `data/` (vidéos, trajectoires, embeddings, zones, metadata…)
	- `outputs/` (events, reports, logs…)
	- `configs/` (fichiers de config + credentials OAuth)
	- `doc/` (documentation interne locale)
	- `oauth.txt`, `.env`, logs, caches…

Conséquence : si tu clones le repo depuis GitHub, tu dois (re)créer `data/` et `configs/` en local (voir sections ci-dessous).

## Prérequis

- Windows 10/11 (le projet tourne aussi généralement sous Linux, mais ce repo est principalement utilisé sous Windows)
- Python 3.10+ (recommandé : 3.11)
- Accès aux vidéos `*.mp4`

### Accélération (optionnel)

- GPU NVIDIA : recommandé si tu veux accélérer YOLO/ReID (PyTorch CUDA)
- CPU only : fonctionne, mais plus lent

Note : le `requirements.txt` de ce workspace contient des versions PyTorch “CUDA” (`+cu121`). Sur une machine sans CUDA, installe plutôt une version CPU de PyTorch et adapte l'installation (voir “Installation”).

## Installation

### 1) Créer un environnement virtuel

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

### 2) Installer les dépendances

Option A — Machine avec CUDA (si compatible avec ton poste) :

```bash
pip install -r requirements.txt
```

Option B — Machine CPU only :

1) Installer PyTorch CPU :

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

2) Installer le reste :

```bash
pip install -r requirements.txt
```

Si pip refuse à cause des wheels `+cu121`, remplace les lignes `torch/torchvision/torchaudio` dans `requirements.txt` par des versions CPU (ou supprime-les du fichier et installe PyTorch séparément comme ci-dessus).

## Données & configuration attendues

Comme `data/` et `configs/` sont ignorés par Git, voici l'arborescence minimale attendue en local :

```text
data/
	videos/                      # fichiers .mp4
	trajectories/                # généré par le pipeline
	embeddings/                  # généré par le pipeline
	camera_offsets_timestamp.json    # optionnel (préféré)
	camera_offsets_durree.json       # optionnel (fallback)
	zones_interdites.json            # recommandé (zones d'intrusion)
	video_orientations.json          # optionnel (rotation par caméra)

configs/
	cameras.json                 # optionnel selon usages
	camera_network.json          # optionnel (topologie/gating)
	credentials.json             # optionnel (Google Drive)
	token.json                   # généré par OAuth
```

Création rapide (Windows) :

```bash
mkdir data\videos
mkdir data\trajectories
mkdir outputs\events
mkdir outputs\reports
mkdir configs
```

### Réseau de caméras (topologie) — optionnel

Le “gating” topologique sert à empêcher des associations ReID impossibles (caméras non atteignables).

- Fichier (local) : `configs/camera_network.json`
- Format d'arêtes :
	- Sans temps : `{ "from": "CAMERA_A", "to": "CAMERA_B" }`
	- Avec temps : `{ "from": "CAMERA_A", "to": "CAMERA_B", "min_s": 3, "max_s": 120 }`

Si tu ne veux pas de gating, mets `"edges": []`.

### Zones interdites (intrusions)

Pour définir les zones, utilise l'outil visuel :

```bash
python src/zones/zone_visual.py
```

Le fichier de sortie est généralement `data/zones_interdites.json`.

Astuce (anti-doublons) : si deux caméras couvrent exactement la même zone physique, donne le même `name` aux zones correspondantes pour faciliter la déduplication.

## Lancer le pipeline

### Pipeline complet (traitement + matching + exports)

```bash
python main.py
```

Options utiles :

- Retraiter toutes les vidéos :

```bash
python main.py --force
```

Important : même si aucune vidéo n'est à retraiter, `main.py` exécute quand même la fin de chaîne (matching global, enrichissement, rapport, exports) tant que `data/trajectories/` existe.

### Version “V” (pipeline + dashboard)

```bash
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

- Trajectoires : `data/trajectories/*.json` (inclut timestamps `t_sync` et embeddings ReID)
- Embeddings exportés : `data/embeddings/<VIDEO_ID>/*.npy` + `data/embeddings/embeddings_index_<RUN_ID>.csv`
- Événements : `outputs/events/events_<RUN_ID>.jsonl`
- Rapport : `outputs/reports/run_report_<RUN_ID>.json` + `outputs/reports/latest.json`
- Exports CSV :
	- `database/personnes.csv`
	- `database/evenements.csv`
	- `database/classes.csv`

### Pourquoi certains fichiers peuvent être vides ?

- Les events (`outputs/events/...`) et `database/evenements.csv` peuvent être vides si aucune intrusion n'a été détectée (zones absentes/inactives, seuil `min_duration` trop élevé, aucune personne dans une zone…).
- `database/classes.csv` est généré à partir des trajectoires (même si 0 vidéo retraitée).

## Notebooks (exploration)

Les notebooks dans `notebooks/` servent à inspecter/valider les exports CSV (personnes, événements, classes, vidéos).

## Sécurité & confidentialité

Ce projet traite des vidéos potentiellement sensibles.

- Ne versionne pas les vidéos/frames/trajectoires/embeddings sur GitHub.
- Ne versionne pas `configs/credentials.json` et `configs/token.json`.
- Utilise des chemins locaux ou des secrets CI si tu automatises.

