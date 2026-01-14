import cv2
import json
import time
import numpy as np
from pathlib import Path
import math
from src.pipeline.global_analysis_v import GlobalAnalyzer


def _stable_color(key: object) -> tuple[int, int, int]:
    """Deterministic pseudo-random color for an id (int/str/etc)."""
    try:
        s = str(key)
    except Exception:
        s = repr(key)
    h = abs(hash(s))
    return ((h * 37) % 255, (h * 17) % 255, (h * 29) % 255)


def _safe_int(v: object) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _apply_rotation(frame: np.ndarray, rotation_deg: int) -> np.ndarray:
    """Rotate frame by 0/90/180/270 degrees."""
    rot = int(rotation_deg) % 360
    if rot == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rot == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rot == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame

class DashboardV:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.videos_dir = self.data_dir / "videos"
        self.traj_dir = self.data_dir / "trajectories"
        self.offsets_durree_file = self.data_dir / "camera_offsets_durree.json"
        self.offsets_timestamp_file = self.data_dir / "camera_offsets_timestamp.json"
        
        self.analyzer = GlobalAnalyzer(data_dir)
        
        self.videos = {} # video_id -> {cap, offset, status, data, current_frame_idx}
        self.global_time = 0.0
        self.target_fps = 30.0
        self.running = False

    def load_resources(self):
        """Loads videos, offsets, and trajectory data."""
        print("[Dashboard] Loading resources...")
        
        # 0. Run Global Analysis
        self.analyzer.load_data()
        
        # 1. Load Offsets (prefer timestamp offsets, fallback to duration offsets)
        offsets_timestamp = {}
        offsets_durree = {}

        if self.offsets_timestamp_file.exists():
            try:
                with open(self.offsets_timestamp_file, "r") as f:
                    offsets_timestamp = json.load(f)
            except Exception:
                offsets_timestamp = {}

        if self.offsets_durree_file.exists():
            try:
                with open(self.offsets_durree_file, "r") as f:
                    offsets_durree = json.load(f)
            except Exception:
                offsets_durree = {}
        
        # 2. Find Videos and Load Data
        video_files = list(self.videos_dir.glob("*.mp4"))
        
        for vpath in video_files:
            # Guess video_id (filename without extension)
            # Note: The offset file uses keys like "CAMERA_X_full". 
            # The video file might be "CAMERA_X.mp4".
            # We need to match them.
            video_name = vpath.stem

            # Default offset from config (will be overridden by trajectory sync_offset if present)
            offset = 0.0
            for key, val in offsets_timestamp.items():
                if video_name in key:
                    try:
                        offset = float(val)
                    except Exception:
                        offset = 0.0
                    break
            if offset == 0.0:
                for key, val in offsets_durree.items():
                    if video_name in key:
                        try:
                            offset = float(val)
                        except Exception:
                            offset = 0.0
                        break
            
            # Load Trajectory Data
            # We assume trajectory file has same name as video_name?
            # Or we look for a json file that contains this video_id?
            # Let's look for json with same stem.
            json_path = self.traj_dir / f"{video_name}.json"
            traj_data = {}
            tracks_by_frame = {} # frame_id -> list of tracks
            rotation_applied = 0
            
            if json_path.exists():
                with open(json_path, "r") as f:
                    traj_data = json.load(f)

                # Prefer the actual sync_offset used during processing (ensures Dashboard matches pipeline)
                try:
                    offset = float(traj_data.get("sync_offset", offset))
                except Exception:
                    pass

                try:
                    rotation_applied = int(traj_data.get("rotation_applied", 0))
                except Exception:
                    rotation_applied = 0
                    
                # Index tracks by frame for fast lookup during playback
                for track in traj_data.get("trajectories", []):
                    gid_val = _safe_int(track.get("global_id"))
                    gid = gid_val if gid_val is not None else track.get("track_id")
                    for fr in track["frames"]:
                        fid = fr["frame"]
                        if fid not in tracks_by_frame:
                            tracks_by_frame[fid] = []
                        
                        tracks_by_frame[fid].append({
                            "id": gid,
                            "bbox": fr["bbox"],
                            "type": "person" # Default
                        })

            # Cache capture properties + compute scale factors once per video
            cap = cv2.VideoCapture(str(vpath))
            w_orig = float(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h_orig = float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

            # If we rotate by 90/270, width/height swap
            rot = int(rotation_applied) % 360
            if rot in (90, 270):
                w_base, h_base = h_orig, w_orig
            else:
                w_base, h_base = w_orig, h_orig

            sx = 1.0
            sy = 1.0
            if w_base > 0:
                sx = 640.0 / w_base
            if h_base > 0:
                sy = 360.0 / h_base
            
            self.videos[video_name] = {
                "path": str(vpath),
                "cap": cap,
                "offset": offset,
                "rotation_applied": rotation_applied,
                "status": "waiting", # waiting, playing, finished
                "tracks": tracks_by_frame,
                "frame_count": 0,
                "sx": sx,
                "sy": sy,
            }
            print(f"Loaded {video_name}: Offset={offset:.1f}s | Rotation={rotation_applied}°")

    def run(self):
        """Main playback loop."""
        self.running = True
        
        # Calculate grid size
        n_videos = len(self.videos)
        cols = math.ceil(math.sqrt(n_videos))
        rows = math.ceil(n_videos / cols)
        
        # Window
        cv2.namedWindow("Dashboard V", cv2.WINDOW_NORMAL)
        
        print(f"[Dashboard] Starting playback. Grid: {cols}x{rows}")
        
        try:
            while self.running:
                start_loop = time.time()
                
                frames_to_show = []
                
                active_videos = 0
                
                for vid_id, vdata in self.videos.items():
                    cap = vdata["cap"]
                    offset = vdata["offset"]
                    rotation_applied = int(vdata.get("rotation_applied", 0))
                    sx = float(vdata.get("sx", 1.0))
                    sy = float(vdata.get("sy", 1.0))
                
                # Determine state
                if self.global_time < offset:
                    vdata["status"] = "waiting"
                elif vdata["status"] != "finished":
                    vdata["status"] = "playing"
                
                # Get Frame
                frame = None
                
                if vdata["status"] == "waiting":
                    # Black frame with text
                    frame = np.zeros((360, 640, 3), dtype=np.uint8)
                    wait_time = offset - self.global_time
                    cv2.putText(frame, f"Starts in {wait_time:.1f}s", (50, 180), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    active_videos += 1
                    
                elif vdata["status"] == "playing":
                    ret, frame = cap.read()
                    if ret:
                        vdata["frame_count"] += 1
                        active_videos += 1

                        # Apply same rotation as used during processing so bboxes align.
                        frame = _apply_rotation(frame, rotation_applied)
                        
                        # Resize for grid (optional, but good for performance)
                        frame = cv2.resize(frame, (640, 360))
                        
                        # Draw Detections
                        # We need to know which frame number corresponds to current time?
                        # Since we read sequentially, vdata["frame_count"] is the current frame index.
                        # Note: frame_count starts at 1 usually in my logic, or 0? 
                        # Let's assume 1-based index from YOLO.
                        current_fid = vdata["frame_count"]
                        
                        detections = vdata["tracks"].get(current_fid, [])
                        for det in detections:
                            x1, y1, x2, y2 = det["bbox"]
                            
                            sx1, sy1 = int(x1*sx), int(y1*sy)
                            sx2, sy2 = int(x2*sx), int(y2*sy)
                            
                            # Color based on ID (robust: works for int or str ids)
                            color = _stable_color(det.get("id"))
                            
                            cv2.rectangle(frame, (sx1, sy1), (sx2, sy2), color, 2)
                            cv2.putText(frame, f"ID {det['id']}", (sx1, sy1-5), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                            
                            # Show History / Alerts if available
                            story = self.analyzer.get_story(det["id"])
                            if story:
                                # Check for active alerts
                                active_alert = None
                                for alert in story["alerts"]:
                                    # Simple check: is alert time close to current time?
                                    if abs(alert["time"] - self.global_time) < 2.0: # Show for 2 seconds
                                        active_alert = alert["zone"]
                                        break
                                
                                if active_alert:
                                    cv2.putText(frame, f"ALERT: {active_alert}", (sx1, sy1-20), 
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                                    
                                # Show path summary (last 3 cameras)
                                # Only show if mouse hover? Or always?
                                # Always might be too much. Let's show only if alert or specific key?
                                # Let's show simple text at bottom of bbox
                                path_str = " -> ".join([p["camera"].replace("CAMERA_", "")[:3] for p in story["path"][-3:]])
                                cv2.putText(frame, path_str, (sx1, sy2+15), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                                        
                    else:
                        vdata["status"] = "finished"
                        frame = np.zeros((360, 640, 3), dtype=np.uint8)
                        cv2.putText(frame, "Finished", (200, 180), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                else: # Finished
                    frame = np.zeros((360, 640, 3), dtype=np.uint8)
                    cv2.putText(frame, "Finished", (200, 180), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                    # Add label
                    cv2.putText(frame, vid_id, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    frames_to_show.append(frame)

                if active_videos == 0 and self.global_time > 10: # Allow some startup time
                    print("All videos finished.")
                    self.running = False
                    break

                # Combine frames into grid
                # Pad with black frames if needed
                while len(frames_to_show) < cols * rows:
                    frames_to_show.append(np.zeros((360, 640, 3), dtype=np.uint8))
                
                # Create rows
                grid_rows = []
                for r in range(rows):
                    row_frames = frames_to_show[r*cols : (r+1)*cols]
                    grid_rows.append(np.hstack(row_frames))
                
                # Create full grid
                final_grid = np.vstack(grid_rows)
                
                # Add Global Time Overlay
                cv2.putText(final_grid, f"Global Time: {self.global_time:.2f}s", (20, 50), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 3)

                cv2.imshow("Dashboard V", final_grid)
                
                # Handle Key Press
                key = cv2.waitKey(1)
                if key == ord('q'):
                    self.running = False
                
                # Update Time
                # We want to sync with real time or fixed fps?
                # Fixed FPS is smoother for replay.
                self.global_time += 1.0 / self.target_fps
                
                # Sleep to maintain FPS (optional, if processing is fast)
                elapsed = time.time() - start_loop
                wait = max(0, (1.0/self.target_fps) - elapsed)
                time.sleep(wait)
        finally:
            for vdata in self.videos.values():
                try:
                    vdata.get("cap").release()
                except Exception:
                    pass
            cv2.destroyAllWindows()

if __name__ == "__main__":
    dashboard = DashboardV()
    dashboard.load_resources()
    dashboard.run()
