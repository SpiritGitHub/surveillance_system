import torch
import torchvision.transforms as T
from torchvision.models import resnet50, ResNet50_Weights
import logging
from PIL import Image
import numpy as np

logger = logging.getLogger("FeatureExtractor")

class FeatureExtractor:
    def __init__(self, device=None):
        self.device = device if device else ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Loading ReID model on {self.device}...")
        
        # Load pre-trained ResNet50
        # We use the default weights (ImageNet) which are decent for general feature extraction
        # For better results, a model trained on Market1501 (like from torchreid) would be better
        # but ResNet50 is a solid, easy-to-install baseline.
        self.model = resnet50(weights=ResNet50_Weights.DEFAULT)
        
        # Remove the classification layer (fc) to get embeddings
        # ResNet50 fc layer input size is 2048
        self.model.fc = torch.nn.Identity()
        
        self.model.to(self.device)
        self.model.eval()
        
        self.transforms = T.Compose([
            T.Resize((256, 128)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        logger.info("FeatureExtractor initialized")

    def extract(self, image):
        """
        Extract embedding from an image (numpy array or PIL Image).
        Returns a numpy array of shape (2048,)
        """
        if isinstance(image, np.ndarray):
            image = Image.fromarray(image)
            
        input_tensor = self.transforms(image).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            embedding = self.model(input_tensor)
            
        # Normalize embedding (important for cosine similarity)
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
        
        return embedding.cpu().numpy().flatten()
