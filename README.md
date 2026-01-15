# Surveillance System — Détection, suivi et analyse multi-caméras

Ce projet transforme des vidéos multi-caméras en données structurées (trajectoires, identités globales, événements) afin de faciliter l'analyse et l'audit (qui est passé où, quand, et pendant combien de temps).

## Fonctionnalités

### 1) Détection multi-objets

Le système détecte automatiquement :

- Personnes
- Véhicules (voitures, motos, bus)
- Bagages (sacs à dos, sacs à main)

### 2) Suivi (tracking) et trajectoires

- Suivi de chaque objet dans une vidéo (identifiants locaux + positions dans le temps).
- Enregistrement de trajectoires exploitables (JSON/CSV).
- Synchronisation temporelle via offsets pour aligner plusieurs caméras sur un temps commun.

### 3) Zones et alertes

- Définition de zones interdites (polygones).
- Détection d'intrusion selon une logique immédiate ou à seuil de durée.

### 4) Ré-identification (Re-ID)

- Regroupement des trajectoires d'une même personne entre caméras.
- Attribution d'un identifiant global (global_id).

### 5) Réseau de caméras (topologie)

Pour améliorer le tracking multi-caméras, le système peut utiliser une **topologie** (qui voit “avant/après” qui) pour éviter des associations ReID impossibles.

- Configuration : [configs/camera_network.json](configs/camera_network.json)
- Effet : le matching global ReID est “gated” par la topologie (on ne compare pas une identité avec une caméra qui ne peut pas être atteinte).

Le format des `edges` peut être :

- **Sans temps (recommandé si tu n'as pas de durées fiables)** : `{ "from": "CAMERA_A", "to": "CAMERA_B" }`
- **Avec temps (optionnel)** : `{ "from": "CAMERA_A", "to": "CAMERA_B", "min_s": 3, "max_s": 120 }`

Si tu ne veux pas de gating topologique, tu peux vider la liste `edges` (comportement permissif, comme avant).

### 6) Enrichissement des événements (avant/après + déduplication)

Après le global matching, le système enrichit les événements d'intrusion avec :

- `global_id` (identité multi-cam)
- `prev_camera` / `next_camera` (où la personne est vue avant/après l'infraction, basé sur `t_sync`)
- `prev_camera_candidates` / `next_camera_candidates` (voisins possibles selon le réseau de caméras)

Cas des caméras très recouvrantes (même scène / même zone) :

- Une déduplication est appliquée pour éviter les doublons d'événements quand la **même zone physique** est définie sur deux caméras voisines.
- Recommandation : donne le **même `name`** aux deux zones (dans `data/zones_interdites.json`) si elles représentent la même zone physique.

## Utilisation

### Étape 1 : Installation

```bash
pip install -r requirements.txt
# Pour le Re-ID (optionnel mais recommandé)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### Étape 2 : Vos Données

1.  Placez vos vidéos dans `data/videos/`.
2.  (Optionnel) Placez votre fichier de synchronisation `camera_offsets_durree.json` dans `data/`.

### Étape 3 : Configuration des Zones

Lancez l'outil visuel pour définir où sont les zones interdites :

```bash
python src/zones/zone_visual.py
```

Suivez les instructions à l'écran (cliquez pour dessiner).

### Étape 4 : Lancer l'Analyse

```bash
python main.py
```

Le système va :

1.  Analyser chaque vidéo (peut prendre du temps).
2.  Détecter, suivre et vérifier les intrusions.
3.  À la fin, relier les personnes entre les caméras (Global Matching).

Important : même si aucune vidéo n'est à retraiter (déjà traité), `main.py` exécute tout de même la fin de chaîne (matching global, rapport, exports) tant que `data/trajectories/` existe.

### Étape 5 : Résultats

- **Trajectoires complètes** : `data/trajectories/*.json` (contient aussi les embeddings ReID des personnes).
- **Embeddings exportés** : `data/embeddings/<VIDEO_ID>/*.npy` + `data/embeddings/embeddings_index_<RUN_ID>.csv`.
- **Événements (intrusions)** : `outputs/events/events_<RUN_ID>.jsonl`.
- **Rapport examinateur** : `outputs/reports/run_report_<RUN_ID>.json` + `outputs/reports/latest.json`.
- **Exports “database”** :
	- `database/personnes.csv`
	- `database/evenements.csv`
	- `database/classes.csv`

#### Pourquoi certains fichiers peuvent être “vides” ?

- `outputs/events/events_<RUN_ID>.jsonl` et `database/evenements.csv` peuvent être vides si **aucune intrusion** n’a été détectée (zones absentes/inactives, seuil `min_duration` trop élevé, aucune personne dans une zone, etc.).
- `database/classes.csv` est généré à partir des trajectoires (même si 0 vidéo retraitée).

