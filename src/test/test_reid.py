import unittest
import sys
from pathlib import Path
import numpy as np

# Add src to path
sys.path.append(str(Path(__file__).parents[2]))

# Mock torch if not installed yet for testing structure?
# No, we want to test real functionality.
# We will assume torch is installed when running this test.

class TestReIDSystem(unittest.TestCase):
    def setUp(self):
        try:
            from src.reid.feature_extractor import FeatureExtractor
            from src.reid.matcher import ReIDMatcher
            self.extractor = FeatureExtractor(device="cpu")
            self.matcher = ReIDMatcher(threshold=0.3)
            self.reid_available = True
        except ImportError:
            self.reid_available = False
            print("Skipping ReID tests: dependencies not found")

    def test_feature_extraction(self):
        if not self.reid_available:
            return
            
        # Create dummy image (H, W, C)
        dummy_image = np.random.randint(0, 255, (128, 64, 3), dtype=np.uint8)
        
        embedding = self.extractor.extract(dummy_image)
        
        # Check shape (ResNet50 default is 2048)
        self.assertEqual(embedding.shape, (2048,))
        
        # Check normalization (norm should be close to 1)
        norm = np.linalg.norm(embedding)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_matching(self):
        if not self.reid_available:
            return
            
        # Create two similar embeddings
        emb1 = np.random.rand(2048)
        emb1 = emb1 / np.linalg.norm(emb1)
        
        # emb2 is close to emb1
        emb2 = emb1 + np.random.normal(0, 0.01, 2048)
        emb2 = emb2 / np.linalg.norm(emb2)
        
        # emb3 is far
        emb3 = -emb1
        
        # Match 1
        gid1 = self.matcher.match_track(emb1, 0.0)
        self.assertEqual(gid1, 1)
        
        # Match 2 (should be same ID)
        gid2 = self.matcher.match_track(emb2, 1.0)
        self.assertEqual(gid2, 1)
        
        # Match 3 (should be new ID)
        gid3 = self.matcher.match_track(emb3, 2.0)
        self.assertNotEqual(gid3, 1)

if __name__ == '__main__':
    unittest.main()
