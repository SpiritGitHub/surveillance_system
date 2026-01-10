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

### Étape 5 : Résultats

- **Intrusions** : Consultez `outputs/events.csv`.
- **Trajectoires complètes** : Dossier `data/trajectories/`.

## 📚 Documentation Détaillée

Pour comprendre exactement comment fonctionne chaque fichier du code, consultez le fichier **[PROJECT_EXPLANATION.md](PROJECT_EXPLANATION.md)**.
