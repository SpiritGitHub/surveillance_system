'''
yolo_detector.py
'''
import cv2
import csv
import time
import logging
from pathlib import Path
from ultralytics import YOLO

# Module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

# YOLOv8 COCO class IDs
# Default set for this project (extend as needed).
# Note: some requested classes (e.g. "helmet") are not in COCO.
USEFUL_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    24: "backpack",
    26: "handbag",
}

class YOLODetector:
    def __init__(
        self,
        model_path: str,
        conf_threshold: float = 0.4,
        frame_skip: int = 1,
        save_debug: bool = False,
        debug_dir: str = "data/frames",
        useful_classes: dict | None = None
    ):
        """
        YOLO detector pour :
        - analyse vidéo offline
        - détection frame par frame (tracking)
        """
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.frame_skip = frame_skip
        self.save_debug = save_debug
        # If None: allow all classes. Otherwise filter to provided class_id->name mapping.
        self.useful_classes = useful_classes

        self.debug_dir = Path(debug_dir)
        self.debug_dir.mkdir(parents=True, exist_ok=True)

        logger.info("YOLODetector initialisé")

    # VIDEO DETECTION
    def detect(self, video_path: str):
        """
        Analyse complète d'une vidéo (mode offline)
        Retourne toutes les détections
        """
        print("\n" + "=" * 60)
        print(f"[YOLO] Démarrage détection vidéo : {video_path}")
        print("=" * 60)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[YOLO][ERREUR] Impossible d'ouvrir la vidéo : {video_path}")
            return []

        frame_id = 0
        processed_frames = 0
        total_frames_read = 0

        detections = []

        total_detections = 0
        empty_frames = 0
        total_inference_time = 0.0

        start_time = time.time()

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            total_frames_read += 1
            frame_id += 1

            # Optimisation FPS
            if frame_id % self.frame_skip != 0:
                continue

            processed_frames += 1

            # ⏱️ Inference YOLO
            t0 = time.time()
            results = self.model(
                frame,
                conf=self.conf_threshold,
                verbose=False
            )[0]
            inference_time = time.time() - t0
            total_inference_time += inference_time

            frame_has_detection = False

            # Optional mapping of useful classes (e.g., {0: 'person', ...})
            useful_classes = self.useful_classes if self.useful_classes is not None else USEFUL_CLASSES

            if results.boxes is not None:
                for box in results.boxes:
                    cls_id = int(box.cls[0])

                    if useful_classes is not None and cls_id not in useful_classes:
                        continue

                    frame_has_detection = True
                    total_detections += 1

                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    class_name = useful_classes[cls_id] if useful_classes is not None else str(cls_id)

                    detection = {
                        "frame_id": frame_id,
                        "class_id": cls_id,
                        "class_name": class_name,
                        "confidence": conf,
                        "bbox": [x1, y1, x2, y2]
                    }

                    detections.append(detection)

                    if self.save_debug:
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(
                            frame,
                            detection["class_name"],
                            (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            1
                        )

            if not frame_has_detection:
                empty_frames += 1

            if self.save_debug:
                cv2.imwrite(
                    str(self.debug_dir / f"frame_{frame_id}.jpg"),
                    frame
                )

        cap.release()

        # PERFORMANCE REPORT - CORRECTION : Utiliser print() au lieu de logger.info()
        elapsed = time.time() - start_time

        fps = processed_frames / elapsed if elapsed > 0 else 0
        avg_frame_time = elapsed / processed_frames if processed_frames else 0
        avg_inference_time = (
            total_inference_time / processed_frames
            if processed_frames else 0
        )

        print("========== YOLO PERFORMANCE REPORT ==========")
        print(f"Vidéo                : {video_path}")
        print(f"Frames lues           : {total_frames_read}")
        print(f"Frames traitées       : {processed_frames}")
        print(f"FPS effectif          : {fps:.2f}")
        print(f"Temps moyen / frame   : {avg_frame_time*1000:.2f} ms")
        print(f"Temps moyen inference : {avg_inference_time*1000:.2f} ms")
        print(f"Détections totales    : {total_detections}")
        print("============================================")

        return detections

    #  FRAME DETECTION (TRACKING)
    def detect_frame(self, frame):
        """
        Détection YOLO sur UNE frame
        Retourne des détections compatibles DeepSORT
        """
        results = self.model(
            frame,
            conf=self.conf_threshold,
            verbose=False
        )[0]
        detections = []

        useful_classes = self.useful_classes if self.useful_classes is not None else USEFUL_CLASSES

        if results.boxes is not None:
            for box in results.boxes:
                cls_id = int(box.cls[0])
                if useful_classes is not None and cls_id not in useful_classes:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                class_name = useful_classes[cls_id] if useful_classes is not None else str(cls_id)

                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": conf,
                    "class_id": cls_id,
                    "class_name": class_name,
                })

        return detections
    