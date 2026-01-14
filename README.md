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

## Documentation

Pour une documentation technique exhaustive (structure, formats, flux end-to-end), voir [doc/TECHNICAL_GUIDE.md](doc/TECHNICAL_GUIDE.md).

Pour une trame de présentation (oral) et une lecture orientée « projet », voir [doc/PRESENTATION.md](doc/PRESENTATION.md).
