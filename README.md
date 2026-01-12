# 🕵️ Surveillance System - Détection et Tracking Intelligent

Ce système transforme un réseau de caméras (ou smartphones) en un système de surveillance intelligent capable de suivre des individus et véhicules à travers plusieurs vues.

## ✨ Fonctionnalités Clés

### 1. Détection Multi-Objets

Le système détecte et identifie automatiquement :

- 👤 **Personnes**
- 🚗 **Véhicules** : Voitures, motos, bus, camions
- 🎒 **Bagages** : Sacs à dos, sacs à main, valises

### 2. Suivi et Trajectoires

- Suit chaque objet individuellement dans la vidéo.
- Enregistre sa trajectoire précise (position, heure).
- **Synchronisation Temporelle** : Utilise un fichier de configuration pour aligner temporellement toutes les vidéos, permettant de savoir exactement ce qui se passe sur toutes les caméras au même instant.

### 3. Sécurité et Alertes

- **Zones Interdites** : Dessinez des zones sur vos vidéos.
- **Détection d'Intrusion** : Recevez une alerte si une personne reste trop longtemps dans une zone sensible.

### 4. Ré-identification (Re-ID)

- Reconnaît la même personne lorsqu'elle passe d'une caméra à une autre.
- Attribue un **Identifiant Unique Global** à chaque individu sur l'ensemble du réseau.

## 🚀 Comment l'utiliser ?

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

💡 Important : même si **0 vidéo** est à retraiter (tout est déjà traité), `main.py` exécute quand même la fin de chaîne (global matching, rapport, exports) tant que `data/trajectories/` existe.

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

## 📚 Documentation Détaillée

Pour comprendre exactement comment fonctionne chaque fichier du code, consultez le fichier **[PROJECT_EXPLANATION.md](PROJECT_EXPLANATION.md)**.

Pour une documentation technique exhaustive (structure + APIs + formats + flux end-to-end), voir **[TECHNICAL_GUIDE.md](TECHNICAL_GUIDE.md)**.
