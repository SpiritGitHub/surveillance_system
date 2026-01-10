# 🛠️ Guide Technique Détaillé

Ce document est destiné aux développeurs ou utilisateurs avancés souhaitant comprendre le fonctionnement interne du système, modifier le code, ou analyser les données brutes.

## 📂 1. Structure Détaillée du Code

### `src/detection/yolo_detector.py`

- **Classe** : `YOLODetector`
- **Entrée** : Chemin vidéo ou Frame (image).
- **Sortie** : Liste de dictionnaires `{'bbox': [x1, y1, x2, y2], 'confidence': 0.9, 'class_id': 0}`.
- **Détails** :
  - Charge le modèle `yolov8n.pt` (nano) pour la rapidité.
  - Filtre les classes via `USEFUL_CLASSES` (Personnes, Véhicules, Sacs).
  - Gère un `frame_skip` pour accélérer le traitement (traiter 1 image sur N).

### `src/tracking/deepsort_tracker.py`

- **Classe** : `DeepSortTracker`
- **Entrée** : Liste de détections YOLO + Frame actuelle.
- **Sortie** : Liste de tracks mis à jour avec `track_id`.
- **Détails** :
  - Utilise l'algorithme DeepSORT (Simple Online and Realtime Tracking with a Deep Association Metric).
  - Gère la disparition temporaire (occlusion) : garde un objet en mémoire pendant `max_age` frames même s'il n'est pas détecté.
  - Stocke l'historique complet des positions dans `self.trajectories`.

### `src/zones/zone_manager.py`

- **Classe** : `ZoneManager`
- **Entrée** : Coordonnées (x, y).
- **Sortie** : Booléen (Est dans la zone ?) ou liste de zones.
- **Détails** :
  - Charge `zones_interdites.json`.
  - Utilise `shapely.geometry.Polygon` pour vérifier `polygon.contains(point)`. C'est très rapide et précis.

### `src/reid/feature_extractor.py`

- **Classe** : `FeatureExtractor`
- **Entrée** : Image rognée (crop) d'une personne.
- **Sortie** : Vecteur (embedding) de taille 2048 (numpy array).
- **Détails** :
  - Utilise un **ResNet50** pré-entraîné (sans la dernière couche de classification).
  - Normalise le vecteur pour que la comparaison (distance cosinus) fonctionne bien.

### `src/pipeline/process_video.py`

- **Fonction** : `process_video(video_path)`
- **Rôle** : Orchestrateur principal.
- **Logique** :
  1.  Initialise tous les modules (YOLO, Tracker, Zones, ReID).
  2.  Charge l'offset de synchronisation depuis `camera_offsets_durree.json`.
  3.  Boucle sur chaque frame de la vidéo :
      - Détecte -> Track -> Vérifie Zones -> Extrait Embedding (toutes les 30 frames).
  4.  Sauvegarde le résultat final dans `data/trajectories/{video_id}.json`.

---

## 💾 2. Formats de Données (JSON & CSV)

### `data/trajectories/*.json`

C'est le fichier le plus important. Il contient TOUT ce qui s'est passé dans une vidéo.

```json
{
  "video_id": "CAMERA_HALL",
  "sync_offset": 12.5,          // Décalage temporel (secondes)
  "rotation_applied": 90,       // Rotation appliquée à l'image
  "stats": { ... },             // Statistiques globales
  "trajectories": [
    {
      "track_id": 1,            // ID local (propre à cette vidéo)
      "global_id": 5,           // ID global (après matching multi-caméras)
      "frames": [
        {
          "frame": 120,         // Numéro de frame
          "t": 4.0,             // Temps relatif (depuis début vidéo)
          "t_sync": 16.5,       // Temps synchronisé (t + sync_offset)
          "bbox": [100, 200, 150, 300], // Position [x1, y1, x2, y2]
          "x": 125, "y": 250    // Centre de l'objet
        },
        ...
      ],
      "embeddings": [ ... ]     // Liste des vecteurs Re-ID (pour debug/matching)
    }
  ]
}
```

### `configs/zones_interdites.json` (ou `data/`)

Définit les zones de sécurité.

```json
{
  "CAMERA_HALL": [
    {
      "zone_id": "ZONE_1",
      "name": "Entrée Interdite",
      "polygon": [
        [10, 10],
        [100, 10],
        [100, 100],
        [10, 100]
      ], // Points (x, y)
      "active": true
    }
  ]
}
```

### `outputs/events.csv`

Journal des alertes. Peut être ouvert dans Excel.

| Colonne     | Description                         |
| :---------- | :---------------------------------- |
| `timestamp` | Date et heure de l'événement        |
| `video_id`  | Caméra concernée                    |
| `track_id`  | ID de la personne                   |
| `zone_id`   | Zone violée                         |
| `duration`  | Temps passé dans la zone (secondes) |
| `frame_id`  | Frame de fin d'événement            |

### `data/camera_offsets_durree.json`

Fichier simple clé-valeur pour la synchronisation.

```json
{
  "CAMERA_HALL": 0.0, // Commence à t=0
  "CAMERA_COULOIR": 15.5 // Commence 15.5 secondes APRES le début de la référence
}
```

---

## ⚙️ 3. Algorithmes Clés

### Synchronisation Temporelle

Le système ne modifie pas les vidéos. Il modifie les **données**.
Si la Caméra A commence à 12h00:00 et la Caméra B à 12h00:10 :

- Un événement à la seconde 5 de la Caméra B s'est réellement passé à 12h00:15.
- Le système calcule : `t_sync = t_video (5s) + offset (10s) = 15s`.
- Cela permet de comparer les événements sur une ligne de temps commune.

### Ré-identification (Global Matching)

1.  On collecte tous les embeddings (signatures visuelles) de toutes les personnes de toutes les vidéos.
2.  On les compare deux à deux avec la **distance cosinus**.
3.  Si la distance < Seuil (0.3), on considère que c'est la même personne.
4.  On regroupe ces identités sous un même `global_id`.
