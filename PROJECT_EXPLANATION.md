# 📘 Explication du Projet : Système de Surveillance Intelligent

## 🎯 Objectif du Projet

Ce projet vise à transformer un ensemble de caméras (ou smartphones) isolées en un **réseau de surveillance intelligent et unifié**.

Contrairement à une surveillance classique où un humain doit regarder des écrans, ce système **analyse automatiquement** le flux vidéo pour :

1.  **Comprendre** ce qui se passe (détecter des objets).
2.  **Suivre** les mouvements (trajectoires).
3.  **Surveiller** les zones sensibles (sécurité).
4.  **Relier** les informations entre plusieurs caméras (ré-identification).

---

## 🏗️ Architecture Globale

Le système fonctionne en **pipeline** (chaîne de traitement). Imaginez une usine où la vidéo brute entre d'un côté et des informations structurées sortent de l'autre.

### Les 4 Piliers du Système

1.  **L'Œil (Détection)** 👁️
    - Utilise l'Intelligence Artificielle (**YOLOv8**) pour "voir" dans l'image.
    - Il ne voit pas juste des pixels, il reconnaît : "C'est une personne", "C'est une voiture", "C'est un sac à dos".
2.  **La Mémoire (Tracking)** 🧠

    - Utilise un algorithme de suivi (**DeepSORT**) pour se souvenir des objets.
    - Si une personne bouge de gauche à droite, le système comprend que c'est la **même** personne, pas une nouvelle apparition à chaque image. Il lui donne un ID (ex: Personne #42).

3.  **Le Gardien (Zones & Alertes)** 🛡️

    - Surveille des zones géographiques précises définies par l'utilisateur.
    - Si une personne entre dans une "Zone Interdite" et y reste, le Gardien déclenche une alerte.

4.  **Le Cerveau Central (Ré-identification)** 🌐
    - C'est la partie la plus complexe. Elle permet de dire : "La personne #42 sur la Caméra A est la même que la personne #12 sur la Caméra B".
    - Cela permet de reconstruire le parcours d'un individu à travers tout le bâtiment.

---

## 🔄 Comment ça marche ? (Le Flux)

1.  **Acquisition** : On récupère les vidéos des différentes caméras.
2.  **Synchronisation** : Comme les caméras ne démarrent pas toutes exactement au même moment, on utilise un fichier de "décalage" (offset) pour aligner leurs horloges. Ainsi, la seconde 10 de la Caméra A correspond bien à la seconde 10 de la Caméra B.
3.  **Traitement Individuel** : Chaque vidéo est analysée indépendamment pour extraire les trajectoires et les événements.
4.  **Fusion (Matching Global)** : Une fois toutes les vidéos traitées, le système compare les "signatures visuelles" (apparence) des personnes pour fusionner les identités à travers le réseau.

## � Pourquoi ce projet est important ?

- **Automatisation** : Plus besoin de surveillance humaine constante.
- **Précision** : L'IA ne se fatigue pas et peut surveiller des dizaines de caméras simultanément.
- **Données** : Le système ne produit pas juste de la vidéo, mais des **données exploitables** (fichiers CSV, JSON) qui peuvent être utilisées pour des statistiques (ex: "Combien de personnes sont passées dans le couloir entre 14h et 15h ?").
