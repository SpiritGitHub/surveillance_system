import unittest
import sys
from pathlib import Path
import time

# Add src to path
sys.path.append(str(Path(__file__).parents[2]))

from src.zones.zone_manager import ZoneManager
from src.alerts.alert_manager import AlertManager

class TestZoneSystem(unittest.TestCase):
    def setUp(self):
        self.zone_manager = ZoneManager(zones_file="test_zones.json")
        self.alert_manager = AlertManager(output_file="test_events.csv", min_duration=1.0)
        
        # Create a test zone
        self.zone_manager.create_zone(
            zone_id="TEST_ZONE",
            name="Test Zone",
            camera_id="CAM_01",
            polygon_points=[(0, 0), (100, 0), (100, 100), (0, 100)],
            description="Test"
        )

    def tearDown(self):
        # Clean up
        Path("test_zones.json").unlink(missing_ok=True)
        Path("test_events.csv").unlink(missing_ok=True)

    def test_point_in_zone(self):
        # Inside
        self.assertTrue(self.zone_manager.is_point_in_zone(50, 50, "TEST_ZONE"))
        # Outside
        self.assertFalse(self.zone_manager.is_point_in_zone(150, 150, "TEST_ZONE"))
        
        # Check all zones
        violations = self.zone_manager.check_point_all_zones(50, 50, "CAM_01")
        self.assertIn("TEST_ZONE", violations)

    def test_alert_generation(self):
        track_id = 1
        video_id = "CAM_01"
        
        # Frame 1: Enter zone (t=0)
        self.alert_manager.update(track_id, ["TEST_ZONE"], 0.0, video_id, 1)
        alerts = self.alert_manager.get_active_alerts(track_id, 0.0)
        self.assertEqual(len(alerts), 0) # Not yet > min_duration (1.0)
        
        # Frame 2: Still in zone (t=0.5)
        self.alert_manager.update(track_id, ["TEST_ZONE"], 0.5, video_id, 2)
        alerts = self.alert_manager.get_active_alerts(track_id, 0.5)
        self.assertEqual(len(alerts), 0)
        
        # Frame 3: Still in zone (t=1.5) -> ALERT
        self.alert_manager.update(track_id, ["TEST_ZONE"], 1.5, video_id, 3)
        alerts = self.alert_manager.get_active_alerts(track_id, 1.5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0][0], "TEST_ZONE")
        
        # Frame 4: Leave zone (t=2.0)
        self.alert_manager.update(track_id, [], 2.0, video_id, 4)
        
        # Check if event was logged
        with open("test_events.csv", "r") as f:
            content = f.read()
            self.assertIn("TEST_ZONE", content)
            self.assertIn("2.00", content) # Duration

if __name__ == '__main__':
    unittest.main()
