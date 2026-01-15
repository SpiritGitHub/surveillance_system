# Guide technique (exhaustif)

Ce document décrit **le projet tel qu’il est dans ce workspace** : chaque dossier, fichier, rôle, dépendances, APIs (classes/fonctions), formats de données et le flux d’exécution “de bout en bout”.

## 0) Roadmap de lecture (étape par étape)

Cette section te donne un ordre simple pour lire le code. L’idée est de comprendre le pipeline du début à la fin, sans se perdre.

### Étape 0 — Pré-requis + organisation des données

- Installe les dépendances avec `pip install -r requirements.txt`.
- Mets les vidéos dans `data/videos/`.
- Définis les zones dans `data/zones_interdites.json`.
- Mets les offsets de synchronisation dans `data/camera_offsets_timestamp.json` (sinon `data/camera_offsets_durree.json`).
- Si tu utilises le multi-cam avancé, configure le réseau dans `configs/camera_network.json`.

Note : `configs/thresholds.yaml` est présent mais vide dans ce workspace. Les réglages importants sont donc surtout dans le code (voir les étapes ci-dessous).

### Étape 1 — Ingestion (optionnelle) : récupérer les vidéos + écrire la metadata

Si tu utilises Google Drive comme source de données, tu as deux fichiers utiles.

- [src/drive/auth.py](src/drive/auth.py) gère l’authentification. Il lit `configs/credentials.json` et enregistre un token dans `configs/token.json`.
- [src/drive/sync_drive_videos.py](src/drive/sync_drive_videos.py) synchronise les vidéos et écrit une metadata dans `data/videos/videos_metadata.json`.

Les réglages principaux sont l’emplacement Drive, les extensions vidéo acceptées, et les retries en cas d’échec réseau.

### Étape 2 — Lancement / orchestration end-to-end

Lis ces fichiers en premier pour comprendre comment tout s’enchaîne.

- [main.py](main.py) est le lanceur principal. Il crée un `run_id`, traite les vidéos nécessaires, puis lance quand même la fin de chaîne (matching global, enrichissement, rapport, exports) si des trajectoires existent.
- [main_v.py](main_v.py) est une variante qui lance ensuite un dashboard synchronisé.

Les options de lancement les plus utiles sont `--force`, `--log-level` et `--no-quiet-external`.

### Étape 3 — Traitement d’une vidéo (détecter → tracker → zones → embeddings)

Cette étape explique comment on transforme une vidéo en trajectoires.

- [src/pipeline/process_video.py](src/pipeline/process_video.py) ouvre la vidéo, applique l’orientation, puis traite la vidéo frame par frame. À la fin, il écrit `data/trajectories/<video_id>.json`.
- À chaque frame, le système fait une détection YOLO, puis un tracking DeepSORT. Il utilise un tracker DeepSORT par classe (person, car, etc.).
- Ensuite, il teste les zones et il met à jour la logique d’intrusion.
- Pour le ReID, il extrait des embeddings seulement pour la classe `person`, et seulement de temps en temps (par défaut environ toutes les 30 frames).

Pour les réglages :

- Le seuil YOLO se règle avec `conf_threshold` (par défaut 0.4).
- La fréquence des embeddings ReID se voit dans `process_video.py` avec la condition `frame_id % 30 == 0`.
- DeepSORT se règle dans [src/tracking/deepsort_tracker.py](src/tracking/deepsort_tracker.py) (par exemple `max_age`, `n_init`, `max_cosine_distance`).

### Étape 4 — Zones interdites + événements d’intrusion

Cette étape transforme des trajectoires en événements d’intrusion.

- [src/zones/zone_manager.py](src/zones/zone_manager.py) charge `data/zones_interdites.json` et permet de tester si une bbox est dans une zone.
- [src/alerts/alert_manager.py](src/alerts/alert_manager.py) garde l’état des intrusions et écrit des événements (`intrusion_confirmed`, puis `intrusion_ended`).

Le réglage principal est `min_duration`. Par défaut, il faut rester 2 secondes dans la zone pour confirmer. Si `min_duration <= 0`, l’intrusion est confirmée dès l’entrée.

### Étape 5 — Synchronisation multi-caméra (timeline commune)

Sans synchronisation, les comparaisons entre caméras deviennent fausses.

- Dans [src/pipeline/process_video.py](src/pipeline/process_video.py), on calcule `sync_offset` depuis `data/camera_offsets_timestamp.json` (prioritaire), sinon depuis `data/camera_offsets_durree.json`.
- Ensuite on calcule `t_sync = t + sync_offset`. C’est ce temps-là qui sert pour les liens multi-cam.

### Étape 6 — Multi-cam : global matching ReID (global_id)

Cette étape donne un identifiant global aux personnes (même personne sur plusieurs caméras).

- [src/pipeline/global_matching.py](src/pipeline/global_matching.py) charge les trajectoires, calcule un embedding représentatif par track, puis écrit un `global_id` dans les JSON.
- [src/reid/matcher.py](src/reid/matcher.py) compare les embeddings avec une distance cosinus.

Les réglages principaux sont `threshold` (seuil de matching) et `max_embeddings_per_track` (nombre d’embeddings utilisés pour la moyenne).

Si tu veux éviter des associations impossibles, tu peux activer le “gating” par topologie avec [src/utils/camera_network.py](src/utils/camera_network.py) et [configs/camera_network.json](configs/camera_network.json).

### Étape 7 — Post-processing : enrichissement + (re)analyse d’intrusions

Cette étape rend les événements plus lisibles et plus utiles.

- [src/utils/event_enricher.py](src/utils/event_enricher.py) ajoute `global_id` dans les events, et calcule `prev_camera` / `next_camera` grâce à `t_sync`.
- [src/zones/intrusion_reanalyzer.py](src/zones/intrusion_reanalyzer.py) peut recréer des événements depuis les trajectoires. C’est utile si tu modifies les zones et que tu veux recalculer vite sans relancer YOLO/DeepSORT.

La reanalyse est faite en mode immédiat (`min_duration=0.0`).

### Étape 8 — Reporting + exports (artefacts examinables)

Cette étape écrit les fichiers de sortie qui servent pour la démo et pour l’analyse.

- [src/utils/run_report.py](src/utils/run_report.py) génère le rapport du run dans `outputs/reports/` (dont `latest.json`).
- [src/utils/embeddings_exporter.py](src/utils/embeddings_exporter.py) exporte les embeddings dans `data/embeddings/` (fichiers `.npy` + index CSV).
- [src/database/exporter.py](src/database/exporter.py) exporte des CSV dans `database/`.

### Étape 9 — Interface (optionnel)

Si tu veux une démo visuelle, tu peux utiliser le dashboard.

- [src/interface/dashboard_v.py](src/interface/dashboard_v.py) affiche plusieurs caméras en lecture synchronisée, avec des overlays et des “histoires” par `global_id`.

## 1) Objectif du projet

Pipeline de surveillance multi-caméras :

- Détection multi-classes (YOLOv8)
- Tracking multi-classes (DeepSORT) **avec un tracker par classe**
- Re-identification (ReID) **uniquement pour `person`** (embeddings ResNet50)
- Synchronisation temporelle via offsets (timeline globale `t_sync`)
- Zones interdites (polygones) + détection d’intrusion (intersection bbox∩zone)
- Journalisation d’événements (JSONL) + enrichissement post-matching (global_id, prev/next camera)
- Rapport de run (JSON) + export “database” (CSV)

## 2) Entrées / Sorties

### Entrées principales

- `data/videos/*.mp4` : vidéos sources.
- `data/camera_offsets_timestamp.json` : offsets de synchronisation (préféré).
- `data/camera_offsets_durree.json` : offsets fallback.
- `data/zones_interdites.json` : zones interdites (polygones).
- `data/video_orientations.json` : orientation (rotation) par vidéo.

### Sorties principales

- `data/trajectories/<VIDEO_ID>.json` : trajectoires + embeddings + timestamps synchronisés.
- `outputs/events/events_<RUN_ID>.jsonl` : événements d’intrusion (JSONL).
- `outputs/reports/run_report_<RUN_ID>.json` + `outputs/reports/latest.json` : rapport pour examinateur.
- `database/personnes.csv` : table globale “personnes” (groupée par `global_id` quand présent).
- `database/evenements.csv` : événements enrichis (global_id, transitions caméras).
- `database/classes.csv` : stats par vidéo/classe (uniques tracks/classe).

Autres sorties (selon options / scripts) :

- `outputs/events/events.csv` : fichier CSV agrégé/historique (présent dans ce workspace). Le pipeline principal écrit surtout en JSONL, puis exporte vers `database/evenements.csv`.
- `outputs/logs/` : logs applicatifs (si activés via les utilitaires de logging).
- `outputs/screenshots/` : captures d’écran/frames (si activé par certains scripts utilitaires).
- `data/frames/` : frames debug (si `YOLODetector(save_debug=True)` est utilisé).

## 3) Flux d’exécution end-to-end

### Lanceur principal

Fichier : [main.py](main.py)

Flux logique :

1. Scan des vidéos et des trajectoires existantes (`TrajectoryValidator`).
2. (Optionnel) retraitement des vidéos manquantes/incomplètes/corrompues, ou `--force` pour tout.
3. Pour chaque vidéo :
   - orientation → détection → tracking multi-classe → zones/intrusions → embeddings ReID (person) → sauvegarde JSON trajectoires.
4. Global matching (ReID) sur toutes les trajectoires → injection `global_id` dans les JSON.
5. Enrichissement des événements JSONL (join video_id/track_id → global_id, et prev/next camera).
6. Génération rapport JSON pour examinateur.
7. Export CSV “database/”.

**Important** : `main.py` a été rendu “end-to-end” : même si aucune vidéo n’est retraitée (déjà à jour), il exécute quand même (si des trajectoires existent) le matching, le rapport et les exports.

## 4) Formats de données

### 4.1 Trajectoires (JSON) : `data/trajectories/<video_id>.json`

Structure (simplifiée) :

```json
{
  "video_id": "CAMERA_...",
  "sync_offset": 12.5,
  "rotation_applied": 90,
  "stats": {
    "frames_processed": 1234,
    "total_detections": 999,
    "total_tracks": 888,
    "unique_by_class": {"person": 5, "car": 2},
    "unique_persons": 5
  },
  "trajectories": [
    {
      "track_id": "person:12",
      "track_local_id": 12,
      "video_id": "CAMERA_...",
      "class_name": "person",
      "class_id": 0,
      "frames": [
        {
          "frame": 1,
          "x": 320,
          "y": 240,
          "t": 0.033,
          "t_sync": 12.533,
          "bbox": [x1,y1,x2,y2]
        }
      ],
      "embeddings": [[...2048...]],
      "global_id": 7
    }
  ]
}
```

Notes :

- `t` est un temps “vidéo” (seconds since start) fourni au tracker.
- `t_sync = t + sync_offset` : temps aligné sur la timeline globale.
- `global_id` est ajouté par [src/pipeline/global_matching.py](src/pipeline/global_matching.py).

### 4.2 Événements (JSONL) : `outputs/events/events_<RUN_ID>.jsonl`

Un événement par ligne JSON.

Champs typiques :


#### 4.2.1 Signification des champs (détaillé)

- `timestamp` : date/heure “humaine” (utile pour logs/lecture). Ce champ n’est pas utilisé pour la synchronisation.
- `event_type` :
  - `intrusion_confirmed` : une intrusion vient d’être confirmée.
  - `intrusion_ended` : la trajectoire est sortie de la zone (fin de l’intrusion).
- `video_id` : identifiant de la vidéo/caméra (ex: `CAMERA_DEBUT_COULOIR_DROIT`).
- `track_id` : identifiant local du tracking, namespacé par classe (ex: `person:21`).
- `class_name` : classe détectée (dans ce projet, les intrusions sont généralement sur `person`).
- `zone_id` : identifiant de la zone interdite (ex: `ZONE_STOCKAGE`).
- `duration` :
  - pour `intrusion_confirmed` : durée passée dans la zone au moment de la confirmation.
    - en **mode immédiat** (`min_duration <= 0`) : `duration` vaut `0.0`.
    - en **mode seuil** : `duration >= min_duration`.
  - pour `intrusion_ended` : durée totale estimée entre entrée et sortie de zone.
- `frame_id` : index de frame (dans la vidéo).
- `t` : temps vidéo (secondes depuis le début de la vidéo), utilisé pendant le tracking.
- `t_sync` : temps global synchronisé : `t_sync = t + sync_offset`.

#### 4.2.2 Champs ajoutés par l’enrichissement (post-processing)

Après `run_global_matching()`, le pipeline exécute `enrich_events_with_global_ids(...)`.

- `global_id` : identifiant global de la personne (même personne à travers plusieurs caméras). Peut être absent si la trajectoire n’a pas d’embeddings exploitables ou si la jointure `(video_id, track_id)` échoue.
- `prev_camera` / `next_camera` : contexte de transition multi-caméra, calculé sur la timeline `t_sync`.
  - Si présent, chaque champ est un objet :
    - `video_id`: caméra précédente/suivante,
    - `track_id`: track correspondant dans cette caméra,
    - `t_start_sync` / `t_end_sync`: intervalle temporel de cette apparition.
- `enriched` : booléen, `true` si l’événement a été enrichi.

#### 4.2.3 Exemple commenté

Extrait typique (JSONL, une ligne = un JSON) :

```json
{
  "timestamp": "2026-01-12 21:19:22",
  "event_type": "intrusion_confirmed",
  "video_id": "CAMERA_DEBUT_COULOIR_DROIT",
  "track_id": "person:21",
  "class_name": "person",
  "zone_id": "ZONE_STOCKAGE",
  "duration": 0.0,
  "frame_id": 1056,
  "t": 38.9028,
  "t_sync": 723.9028,
  "global_id": 1,
  "prev_camera": {"video_id": "CAMERA_HALL_PORTE_GAUCHE", "track_id": "person:66", "t_start_sync": 720.29, "t_end_sync": 722.36},
  "next_camera": {"video_id": "CAMERA_ESCALIER_DEBUT_COULOIR_GAUCHE", "track_id": "person:1", "t_start_sync": 725.24, "t_end_sync": 802.32},
  "enriched": true
}
```

Lecture “humaine” :

- À `t_sync≈723.9s`, la personne `global_id=1` est entrée dans `ZONE_STOCKAGE` sur la caméra `CAMERA_DEBUT_COULOIR_DROIT`.
- `duration=0.0` indique que l’on était en **mode intrusion immédiat**.
- Le système estime qu’avant, cette même personne était visible sur `CAMERA_HALL_PORTE_GAUCHE` et ensuite sur `CAMERA_ESCALIER_DEBUT_COULOIR_GAUCHE`.

#### 4.2.4 Pourquoi on a souvent des paires (confirmed + ended)

Le logger d’intrusion écrit des événements par **intervalle** :

- un `intrusion_confirmed` au moment où l’intrusion devient “valide”,
- puis un `intrusion_ended` quand la trajectoire sort (ou disparaît et qu’on flush).

Ce n’est pas un événement par frame : c’est volontaire pour éviter un “spam” d’événements.


### 4.4 Rapport de run (JSON) : `outputs/reports/run_report_<RUN_ID>.json` et `outputs/reports/latest.json`

Rôle : document “examinateur” qui résume le run (même si 0 vidéos ont été retraitées).

Champs principaux (structure) :

```json
{
  "run": {"run_id": "...", "videos_total": 0, "events_file": "..."},
  "videos": {"count": 0, "summary": {"frames_processed_total": 0, "total_tracks": 0}},
  "events": {"path": "...", "summary": {"total": 262, "by_type": {...}, "by_zone": {...}}},
  "global_matching": {"tracks_with_embeddings": 1137, "unique_identities": 19, "threshold": 0.5},
  "global_ids": {"per_video": {...}, "total_unique_global_ids": 19},
  "embeddings_export": {"out_dir": "data/embeddings", "tracks_exported": 1137, "index_csv": "..."},
  "events_enrichment": {"events_enriched": 262, "events_with_global_id": 258},
  "events_reanalysis": {"videos_scanned": 11, "frames_scanned": 430413},
  "database_export": {"personnes": {"rows": 39}, "evenements": {"rows_appended": 262}, "classes": {"rows": 42}}
}
```

Note : certaines sections peuvent être absentes selon le contexte (ex: pas de zones → pas de reanalysis).

### 4.5 Export embeddings (fichiers .npy + index) : `data/embeddings/`

Rôle : avoir une sortie dédiée “embeddings” (en plus de la présence dans les trajectoires JSON).

- Dossier par caméra : `data/embeddings/<VIDEO_ID>/...`
- Un fichier `.npy` par track `person` qui a des embeddings.
- Index : `data/embeddings/embeddings_index_<RUN_ID>.csv`.

Colonnes de l’index (CSV) :

- `run_id`, `video_id`, `track_id`, `class_name`, `global_id` (si présent),
- `n_embeddings` (combien d’embeddings ont été utilisés),
- `embedding_mode` (ex: `mean`),
- `embedding_file` (chemin vers le `.npy`).

### 4.6 Zones interdites (JSON) : `data/zones_interdites.json`

Fichier créé/modifié par l’éditeur visuel [src/zones/zone_visual.py](src/zones/zone_visual.py).

Structure typique :

```json
{
  "ZONE_STOCKAGE": {
    "zone_id": "ZONE_STOCKAGE",
    "name": "Stockage",
    "camera_id": "CAMERA_DEBUT_COULOIR_DROIT",
    "polygon": [[x1,y1],[x2,y2],[x3,y3]],
    "description": "...",
    "active": true,
    "area": 12345
  }
}
```

Note importante : `ZoneManager` normalise `camera_id` (avec ou sans préfixe `CAMERA_`) pour éviter les mismatches.

### 4.7 Orientations vidéos (JSON) : `data/video_orientations.json`

Fichier écrit par `ManualOrientationDetector`.

- Clé : `video_id`
- Valeur : nombre de rotations (multiples de 90°) ou une forme équivalente selon l’implémentation.

But : garantir que les bboxes et les zones sont cohérentes (même repère image).

- `database/personnes.csv` : construit à partir des trajectoires, regroupé par `global_id` si présent.
- `database/evenements.csv` : conversion des JSONL + déduplication par `event_uid`.
- `database/classes.csv` : stats (unique tracks par classe / vidéo / run).

## 5) Dossiers et fichiers (rôle + API)

### 5.1 Racine du projet

#### [main.py](main.py)

Rôle : orchestrateur batch end-to-end.

Fonction :

- `main(force_reprocess: bool = False) -> None`
  - Calcule `run_id`.
  - Produit `outputs/events/events_<run_id>.jsonl` et `outputs/reports/run_report_<run_id>.json`.
  - Retraite les vidéos nécessaires (ou tout en `--force`).
  - Lance `run_global_matching()` si des trajectoires existent.
  - Enrichit les events via `enrich_events_with_global_ids()`.
  - Écrit un rapport via `write_run_report()`.
  - Exporte les CSV via `export_database()`.

#### [main_v.py](main_v.py)

Rôle : version “V” avec dashboard synchronisé.

Flux :

1. Traite les vidéos manquantes (comme `main.py`, mais sans events per-run).
2. Lance le global matching.
3. Démarre l’interface [src/interface/dashboard_v.py](src/interface/dashboard_v.py).

### 5.2 `src/pipeline/`

#### [src/pipeline/process_video.py](src/pipeline/process_video.py)

Rôle : traitement vidéo complet.

Classes / fonctions :

- `class VideoProcessor(...)`
  - `__init__(model_path, conf_threshold, show_video=False, event_output_file: str|None=None)`
    - Initialise :
      - `YOLODetector` (multi-classes)
      - `ManualOrientationDetector`
      - `ZoneManager`
      - `AlertManager` (écrit dans JSONL/CSV selon extension)
      - `FeatureExtractor` (ReID) si disponible
    - Charge offsets :
      - `data/camera_offsets_timestamp.json` (prioritaire)
      - fallback `data/camera_offsets_durree.json`

  - `process(video_path: str) -> dict|None`
    - Phase 1 : orientation (choix utilisateur, persistée).
    - Phase 2 : tracking multi-classe :
      - `detections = YOLODetector.detect_frame(frame)`
      - group par `class_name`.
      - un `DeepSortTracker(video_id, class_name, class_id)` par classe.
      - timestamps : `video_time = frame_id / fps`.
    - Zones/alertes :
      - appelle `ZoneManager.check_bbox_all_zones(bbox, video_id)`
      - appelle `AlertManager.update(...)`.
    - ReID : toutes les 30 frames pour `person` uniquement :
      - crop bbox → `FeatureExtractor.extract(crop)`
      - `DeepSortTracker.add_embedding(track_id, embedding)`.
    - Sauvegarde : `data/trajectories/<video_id>.json`.

- `process_video(video_path: str, show_video=False, event_output_file: str|None=None)`
  - Helper CLI-friendly qui instancie `VideoProcessor`.

Libs : `opencv-python`, `ultralytics`, `deep_sort_realtime`, `shapely`, `torch/torchvision`.

#### [src/pipeline/global_matching.py](src/pipeline/global_matching.py)

Rôle : ReID global (liaison multi-caméras) et update des JSON trajectories.

Fonction :

- `run_global_matching(data_dir="data/trajectories", threshold=0.5, max_embeddings_per_track=5) -> dict`
  - Charge tous les `*.json`.
  - Ne conserve que les tracks `class_name == "person"` (ou `class_name` absent = compat).
  - Calcule un embedding “représentatif” : moyenne des `N` premiers embeddings.
  - Appelle `ReIDMatcher.match_track(emb, timestamp)`.
  - Écrit `global_id` dans chaque track correspondant.
  - Retourne des stats (files, tracks, unique identities, etc.).

#### [src/pipeline/global_analysis_v.py](src/pipeline/global_analysis_v.py)

Rôle : analyse globale pour l’interface V (histoires par `global_id`).

- `class GlobalAnalyzer` :
  - `load_data()` agrège des segments par `global_id`.
  - Construit `stories[gid] = {path, alerts, first_seen, last_seen, ...}`.

Note : le module recalcule les intrusions à partir des centres de bbox via `ZoneManager.check_point_all_zones(...)`.

### 5.3 `src/detection/`

#### [src/detection/yolo_detector.py](src/detection/yolo_detector.py)

Rôle : encapsulation YOLOv8.

- Constante `USEFUL_CLASSES` : mapping COCO class_id → nom.
- `class YOLODetector` :
  - `__init__(model_path, conf_threshold=0.4, frame_skip=1, save_debug=False, debug_dir="data/frames", useful_classes=None)`
  - `detect(video_path)` : mode offline (retourne une liste de détections).
  - `detect_frame(frame)` : mode frame-by-frame (retourne liste {bbox, confidence, class_id, class_name}).

Libs : `ultralytics`, `opencv-python`.

### 5.4 `src/tracking/`

#### [src/tracking/deepsort_tracker.py](src/tracking/deepsort_tracker.py)

Rôle : wrapper DeepSORT + persist de trajectoires.

- `class DeepSortTracker(video_id, class_name="person", class_id=None)`
  - `update(detections, frame, timestamp=None) -> list[dict]`
    - Convertit YOLO bbox → DeepSORT `[l,t,w,h]`.
    - Renvoie des tracks avec `track_id` namespacé : `"{class_name}:{track_id}"`.
    - Alimente `self.trajectories[track_uid]["frames"]`.
  - `add_embedding(track_id, embedding)` : stocke dans `trajectory["embeddings"]`.
  - `get_trajectories() -> dict` : renvoie toutes les trajectoires + stats dérivées.

Libs : `deep_sort_realtime`.

### 5.5 `src/reid/`

#### [src/reid/feature_extractor.py](src/reid/feature_extractor.py)

Rôle : extraction d’embeddings ReID (baseline).

- `class FeatureExtractor(device=None)`
  - modèle : `torchvision.models.resnet50(weights=DEFAULT)`
  - remplace `fc` par `Identity()` pour obtenir un vecteur 2048.
  - `extract(image) -> np.ndarray (2048,)` + normalisation L2.

Libs : `torch`, `torchvision`, `PIL`.

#### [src/reid/matcher.py](src/reid/matcher.py)

Rôle : matching global via distance cosinus.

- `class ReIDMatcher(threshold=0.3)`
  - `match_track(track_embedding, timestamp) -> int`
    - compare au min des distances cosinus avec embeddings stockés.
    - si < seuil : réutilise l’id, sinon crée un nouvel id.

Libs : `numpy`, `scipy`.

#### [src/reid/person_database.py](src/reid/person_database.py)

Rôle : ancien export “personnes intra-vidéo” vers `data/personnes.csv`.

Note : le système actuel exporte plutôt via [src/database/exporter.py](src/database/exporter.py) dans `database/personnes.csv` (global_id-aware).

#### [src/reid/build_person_db.py](src/reid/build_person_db.py)

Rôle : script CLI milestone (Jour 21) pour générer `data/personnes.csv` via `PersonDatabase`.

### 5.6 `src/zones/`

#### [src/zones/zone_manager.py](src/zones/zone_manager.py)

Rôle : gestion zones interdites + géométrie.

- `class ZoneManager(zones_file="data/zones_interdites.json")`
  - `create_zone(zone_id, name, camera_id, polygon_points, description="")`
  - `is_point_in_zone(x, y, zone_id) -> bool`
  - `check_point_all_zones(x, y, camera_id=None) -> list[str]`
  - `check_bbox_all_zones([x1,y1,x2,y2], camera_id=None) -> list[str]` (utilisé en prod)
  - `save_zones()` / `load_zones()` / activate/deactivate/delete

Libs : `shapely`.

#### [src/zones/zone_visual.py](src/zones/zone_visual.py)

Rôle : éditeur visuel pour créer des zones, au même timestamp sur toutes les caméras.

Libs : `opencv-python`, `numpy`.

#### [src/zones/intrusion_reanalyzer.py](src/zones/intrusion_reanalyzer.py)

Rôle : reconstruire des événements d’intrusion **à partir des trajectoires**.

- Utilisé par [main.py](main.py) si le fichier d’événements est vide mais que les trajectoires existent.
- Force un mode “immédiat” (`min_duration=0.0`) pour produire des intervalles confirmed/ended sans relancer la vision.

### 5.7 `src/alerts/`

#### [src/alerts/alert_manager.py](src/alerts/alert_manager.py)

Rôle : machine d’état intrusions + logging.

- `class AlertManager(output_file="outputs/events/events.jsonl", min_duration=2.0)`
  - `update(track_id, zone_ids, frame_time, video_id, frame_id, class_name=None, t_sync=None)`
    - démarre intrusion à l’entrée.
    - confirme après `min_duration` → `intrusion_confirmed`.
    - log `intrusion_ended` à la sortie si confirmé.
  - `log_event(...)` écrit en CSV ou JSONL.
  - `get_active_alerts(track_id, current_time)` pour la visualisation.

#### [src/alerts/notifier.py](src/alerts/notifier.py)

Rôle : placeholder (fichier vide actuellement).

### 5.8 `src/utils/`

#### [src/utils/trajectory_validator.py](src/utils/trajectory_validator.py)

Rôle : déterminer quelles vidéos doivent être retraitées.

- `TrajectoryValidator.scan_all_videos()` : détecte COMPLETE/MISSING/INCOMPLETE/CORRUPTED.
- Déduplication MP4 case-insensitive (`.mp4`/`.MP4`) par stem.

#### [src/utils/orientation.py](src/utils/orientation.py)

Rôle : sélection manuelle de rotation 0/90/180/270 et persistance dans `data/video_orientations.json`.

#### [src/utils/run_report.py](src/utils/run_report.py)

Rôle : générer un rapport JSON complet.

- `write_run_report(output_path, run_info, per_video_stats, events_path=None, global_matching_info=None, trajectories_dir=None) -> dict`
- Inclut : stats vidéos, top classes, résumé events, infos global matching, `global_ids` (par vidéo + total).

#### [src/utils/event_enricher.py](src/utils/event_enricher.py)

Rôle : enrichir les events JSONL après matching.

- `enrich_events_with_global_ids(events_path, trajectories_dir="data/trajectories", in_place=True) -> dict`
  - joint (video_id, track_id) → `global_id`.
  - calcule `prev_camera`/`next_camera` sur timeline `t_sync`.

#### [src/utils/camera_network.py](src/utils/camera_network.py)

Rôle : modèle de topologie de caméras (graphe) pour “gating” multi-cam.

- Charge [configs/camera_network.json](configs/camera_network.json).
- API principale : `CameraNetwork.allowed_transition(prev_camera, new_camera, dt_s)`.
- Paramètres côté config : `edges[]` (optionnels `min_s/max_s`), `default_max_gap_s`, `allow_same_camera_match`.

#### [src/utils/embeddings_exporter.py](src/utils/embeddings_exporter.py)

Rôle : exporter des embeddings ReID des trajectoires vers `data/embeddings/`.

- Un fichier `.npy` par track + un index CSV `embeddings_index_<RUN_ID>.csv`.
- Paramètres importants : `mode` (`mean`/`first`), `max_embeddings_per_track`.

#### [src/utils/logger.py](src/utils/logger.py)

Rôle : setup logging dans `outputs/logs/`.

#### [src/utils/frame_saver.py](src/utils/frame_saver.py)

Rôle : sauver des frames annotées + JSON metadata par frame.

#### [src/utils/syncro_video_auto.py](src/utils/syncro_video_auto.py)

Rôle : calcul automatique d’offsets via timestamps/durées, persistance dans `data/camera_offsets.json`.

#### [src/utils/syncro_video_man.py](src/utils/syncro_video_man.py)

Rôle : synchronisation manuelle (player double) et sauvegarde offsets.

#### [src/utils/multi_video_viewer.py](src/utils/multi_video_viewer.py)

Rôle : lecteur multi-caméras en grille, même timestamp de départ.

#### [src/utils/metadata_extractor.py](src/utils/metadata_extractor.py)

Rôle : extraction exhaustive de métadonnées via OpenCV, MediaInfo, ffprobe + Drive.

### 5.9 `src/database/`

#### [src/database/exporter.py](src/database/exporter.py)

Rôle : exporter les artefacts examinables vers `database/`.

- `export_personnes_from_trajectories(trajectories_dir, output_csv) -> dict`
- `export_evenements_from_events_jsonl(events_jsonl, output_csv, run_id=None) -> dict`
- `export_classes_per_video(per_video_stats, output_csv, run_id=None) -> dict`
- `export_database(...) -> dict` : wrapper.

### 5.10 `src/metadata/`

#### [src/metadata/metadata_manager.py](src/metadata/metadata_manager.py)

Rôle : extraction de métadonnées “projet” (fps, duration, config caméra, Drive).

Libs : `pymediainfo`, `opencv-python`.

### 5.11 `src/drive/`

#### [src/drive/auth.py](src/drive/auth.py)

Rôle : OAuth Google Drive (lit `configs/credentials.json`, écrit `configs/token.json`).

Libs : `google-auth-oauthlib`, `google-auth`.

#### [src/drive/sync_drive_videos.py](src/drive/sync_drive_videos.py)

Rôle : synchroniser/télécharger les vidéos depuis un dossier Drive.

Libs : `googleapiclient`, `tenacity`, `tqdm`, `loguru`.

### 5.12 `src/interface/`

#### [src/interface/dashboard_v.py](src/interface/dashboard_v.py)

Rôle : lecture synchronisée en grille + overlay bbox + alertes/histoires.

Libs : `opencv-python`, `numpy`.

### 5.13 `src/test/`

Tests (unittest) :

- [src/test/test_reid.py](src/test/test_reid.py) : sanity ReID (shape 2048, norm ~1, matching).
- [src/test/test_zones.py](src/test/test_zones.py) : zones + AlertManager (CSV).
- [src/test/test_env.py](src/test/test_env.py) : check imports YOLO/OpenCV.

Note : les notebooks de test ont été retirés (les notebooks “projet” sont dans `notebooks/`).

## 6) Dépendances (principales)

- Détection : `ultralytics`, `opencv-python`.
- Tracking : `deep-sort-realtime`.
- ReID : `torch`, `torchvision`, `scipy`, `numpy`, `Pillow`.
- Zones : `shapely`.
- Drive : `google-api-python-client`, `google-auth-oauthlib`, `tenacity`, `loguru`, `tqdm`.
- Reporting/export : `json`, `csv` (stdlib).

## 7) Comment lancer

- Traitement end-to-end : `python main.py`
- Forcer retraitement complet : `python main.py --force`
- Dashboard : `python main_v.py`

## 8) Points d’attention (design)

- ReID global limité aux `person` (embeddings calculés seulement sur cette classe).
- Les événements peuvent rester vides si aucune intrusion n’est détectée (zones absentes, seuil trop élevé, etc.).
- Certains scripts “outils” historiques ne sont pas alignés sur les APIs actuelles (ex: `GlobalAnalyzer` et `ZoneManager`).
