"""
Définition de polygones et vérification point ∈ polygone
"""

import json
from pathlib import Path
from shapely.geometry import Point, Polygon
from typing import List, Dict, Tuple


class ZoneManager:
    """Gestionnaire des zones interdites"""
    
    def __init__(self, zones_file="data/zones_interdites.json"):
        self.zones_file = Path(zones_file)
        self.zones_file.parent.mkdir(parents=True, exist_ok=True)
        self.zones = {}
        
        # Charger les zones si le fichier existe
        if self.zones_file.exists():
            self.load_zones()
    @staticmethod
    def _normalize_camera_id(camera_id: str | None) -> str | None:
        if camera_id is None:
            return None
        cam = str(camera_id).strip()
        cam_up = cam.upper()
        if cam_up.startswith("CAMERA_"):
            cam = cam[len("CAMERA_") :]
        return cam

    @classmethod
    def _camera_matches(cls, zone_camera_id: str | None, query_camera_id: str | None) -> bool:
        if query_camera_id is None:
            return True
        return cls._normalize_camera_id(zone_camera_id) == cls._normalize_camera_id(query_camera_id)


        

        
    
    def create_zone(
        self, 
        zone_id: str, 
        name: str, 
        camera_id: str, 
        polygon_points: List[Tuple[int, int]],
        description: str = ""
    ):
        """
        Crée une nouvelle zone interdite
        
        Args:
            zone_id: Identifiant unique de la zone
            name: Nom de la zone
            camera_id: ID de la caméra concernée
            polygon_points: Liste de points [(x1, y1), (x2, y2), ...]
            description: Description optionnelle
        """
        if len(polygon_points) < 3:
            raise ValueError("Un polygone doit avoir au moins 3 points")
        
        # Créer le polygone Shapely
        try:
            polygon = Polygon(polygon_points)
            if not polygon.is_valid:
                raise ValueError("Polygone invalide (auto-intersection ?)")
        except Exception as e:
            raise ValueError(f"Erreur création polygone: {e}")
        
        # Enregistrer la zone
        self.zones[zone_id] = {
            "zone_id": zone_id,
            "name": name,
            "camera_id": camera_id,
            "polygon": polygon_points,
            "description": description,
            "active": True,
            "area": int(polygon.area)
        }
        
        print(f"[ZONES] ✓ Zone créée: {zone_id} ({name}) - {len(polygon_points)} points")
    
    def is_point_in_zone(self, x: int, y: int, zone_id: str) -> bool:
        """
        Vérifie si un point est dans une zone
        
        Args:
            x, y: Coordonnées du point
            zone_id: ID de la zone à vérifier
            
        Returns:
            bool: True si le point est dans la zone
        """
        if zone_id not in self.zones:
            return False
        
        zone = self.zones[zone_id]
        
        # Vérifier si la zone est active
        if not zone.get("active", True):
            return False
        
        # Créer le point et le polygone
        point = Point(x, y)
        polygon = Polygon(zone["polygon"])
        
        return polygon.contains(point)
    
    def check_point_all_zones(self, x: int, y: int, camera_id: str = None) -> List[str]:
        """
        Vérifie si un point est dans une ou plusieurs zones
        
        Args:
            x, y: Coordonnées du point
            camera_id: Filtrer par caméra (optionnel)
            
        Returns:
            list: Liste des IDs de zones contenant le point
        """
        violations = []
        
        for zone_id, zone in self.zones.items():
            # Filtrer par caméra si spécifié
            if camera_id and not self._camera_matches(zone.get("camera_id"), camera_id):
                continue
            
            if self.is_point_in_zone(x, y, zone_id):
                violations.append(zone_id)
        
        return violations

    def check_bbox_all_zones(self, bbox: List[int], camera_id: str = None) -> List[str]:
        """Check which zones intersect a bbox.

        Args:
            bbox: [x1, y1, x2, y2]
            camera_id: optional camera filter

        Returns:
            List of zone_ids intersecting the bbox.
        """
        try:
            x1, y1, x2, y2 = bbox
            rect = Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])
        except Exception:
            return []

        violations = []
        for zone_id, zone in self.zones.items():
            if camera_id and not self._camera_matches(zone.get("camera_id"), camera_id):
                continue
            if not zone.get("active", True):
                continue
            poly = zone.get("_polygon_obj")
            if poly is None:
                poly = Polygon(zone["polygon"])
            # Use intersects so edge-touch counts as intrusion
            if poly.intersects(rect):
                violations.append(zone_id)

        return violations
    
    def get_zones_for_camera(self, camera_id: str) -> Dict:
        """Retourne toutes les zones d'une caméra"""
        return {
            zid: zone for zid, zone in self.zones.items() 
            if self._camera_matches(zone.get("camera_id"), camera_id)
        }
    
    def save_zones(self):
        """Sauvegarde les zones dans le fichier JSON"""
        # Convertir en format sérialisable
        zones_data = {}
        for zone_id, zone in self.zones.items():
            zones_data[zone_id] = {
                "zone_id": zone["zone_id"],
                "name": zone["name"],
                "camera_id": zone["camera_id"],
                "polygon": zone["polygon"],
                "description": zone.get("description", ""),
                "active": zone.get("active", True),
                "area": zone.get("area", 0)
            }
        
        with open(self.zones_file, 'w', encoding='utf-8') as f:
            json.dump(zones_data, f, indent=2, ensure_ascii=False)
        
        print(f"[ZONES] ✓ {len(zones_data)} zone(s) sauvegardée(s) dans {self.zones_file}")
    
    def load_zones(self):
        """Charge les zones depuis le fichier JSON"""
        try:
            with open(self.zones_file, 'r', encoding='utf-8') as f:
                zones_data = json.load(f)
            
            self.zones = zones_data
            print(f"[ZONES] ✓ {len(self.zones)} zone(s) chargée(s)")
            for zone in self.zones.values():
                zone["_polygon_obj"] = Polygon(zone["polygon"])

        except Exception as e:
            print(f"[ZONES] ⚠️  Erreur chargement: {e}")
            self.zones = {}
    
    def deactivate_zone(self, zone_id: str):
        """Désactive temporairement une zone"""
        if zone_id in self.zones:
            self.zones[zone_id]["active"] = False
            print(f"[ZONES] ⏸️  Zone désactivée: {zone_id}")
    
    def activate_zone(self, zone_id: str):
        """Réactive une zone"""
        if zone_id in self.zones:
            self.zones[zone_id]["active"] = True
            print(f"[ZONES] ▶️  Zone activée: {zone_id}")
    
    def delete_zone(self, zone_id: str):
        """Supprime une zone"""
        if zone_id in self.zones:
            del self.zones[zone_id]
            print(f"[ZONES] 🗑️  Zone supprimée: {zone_id}")
    
    def print_summary(self):
        """Affiche un résumé des zones"""
        print("\n" + "=" * 70)
        print("🚨 ZONES INTERDITES")
        print("=" * 70)
        
        if not self.zones:
            print("Aucune zone définie")
            return
        
        # Grouper par caméra
        by_camera = {}
        for zone in self.zones.values():
            cam = zone["camera_id"]
            if cam not in by_camera:
                by_camera[cam] = []
            by_camera[cam].append(zone)
        
        print(f"\nTotal: {len(self.zones)} zone(s) sur {len(by_camera)} caméra(s)")
        
        for camera, zones in sorted(by_camera.items()):
            print(f"\n📹 {camera}:")
            for zone in zones:
                status = "✓" if zone.get("active", True) else "✗"
                print(f"  {status} {zone['zone_id']}: {zone['name']}")
                print(f"      → {len(zone['polygon'])} points, {zone.get('area', 0)} px²")
                if zone.get("description"):
                    print(f"      → {zone['description']}")
        
        print("=" * 70)
    
    def create_example_zones(self):
        """Crée des zones d'exemple pour démonstration"""
        print("\n[ZONES] 📝 Création de zones d'exemple...")
        
        # Zone 1: Bureau du directeur (exemple)
        self.create_zone(
            zone_id="ZONE_BUREAU_DIRECTEUR",
            name="Bureau du Directeur",
            camera_id="HALL_PORTE_ENTREE",
            polygon_points=[
                (100, 100), (400, 100), (400, 300), (100, 300)
            ],
            description="Accès restreint - Bureau de la direction"
        )
        
        # Zone 2: Salle serveur (exemple)
        self.create_zone(
            zone_id="ZONE_SALLE_SERVEUR",
            name="Salle Serveur",
            camera_id="FIN_COULOIR_DROIT",
            polygon_points=[
                (800, 200), (1100, 200), (1100, 500), (800, 500)
            ],
            description="Accès technique restreint"
        )
        
        # Zone 3: Zone de stockage (exemple)
        self.create_zone(
            zone_id="ZONE_STOCKAGE",
            name="Zone de Stockage",
            camera_id="DEBUT_COULOIR_DROIT",
            polygon_points=[
                (50, 400), (250, 400), (250, 650), (50, 650)
            ],
            description="Matériel sensible"
        )
        
        self.save_zones()
        self.print_summary()


# Point d'entrée pour tests
if __name__ == "__main__":
    # Test du système
    manager = ZoneManager()
    
    # Créer des zones d'exemple
    manager.create_example_zones()
    
    # Test de vérification
    print("\n[TEST] Vérification de points:")
    
    # Point dans la zone 1
    x, y = 200, 200
    violations = manager.check_point_all_zones(x, y, camera_id="HALL_PORTE_ENTREE")
    print(f"Point ({x}, {y}): {len(violations)} violation(s) - {violations}")
    
    # Point hors zone
    x, y = 600, 600
    violations = manager.check_point_all_zones(x, y, camera_id="HALL_PORTE_ENTREE")
    print(f"Point ({x}, {y}): {len(violations)} violation(s) - {violations}")