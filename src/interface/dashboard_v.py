import cv2
import json
import time
import numpy as np
from pathlib import Path
import math
from src.pipeline.global_analysis_v import GlobalAnalyzer

class DashboardV:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.videos_dir = self.data_dir / "videos"
        self.traj_dir = self.data_dir / "trajectories"
        self.offsets_file = self.data_dir / "camera_offsets_durree.json"
        
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
        
        # 1. Load Offsets
        offsets = {}
        if self.offsets_file.exists():
            with open(self.offsets_file, "r") as f:
                offsets = json.load(f)
        
        # 2. Find Videos and Load Data
        video_files = list(self.videos_dir.glob("*.mp4"))
        
        for vpath in video_files:
            # Guess video_id (filename without extension)
            # Note: The offset file uses keys like "CAMERA_X_full". 
            # The video file might be "CAMERA_X.mp4".
            # We need to match them.
            video_name = vpath.stem
            
            # Try to find matching offset key
            offset = 0.0
            matched_key = None
            for key in offsets:
                if video_name in key: # Simple substring match
                    offset = float(offsets[key])
                    matched_key = key
                    break
            
            # Load Trajectory Data
            # We assume trajectory file has same name as video_name?
            # Or we look for a json file that contains this video_id?
            # Let's look for json with same stem.
            json_path = self.traj_dir / f"{video_name}.json"
            traj_data = {}
            tracks_by_frame = {} # frame_id -> list of tracks
            
            if json_path.exists():
                with open(json_path, "r") as f:
                    traj_data = json.load(f)
                    
                # Index tracks by frame for fast lookup during playback
                for track in traj_data.get("trajectories", []):
                    gid = track.get("global_id", track["track_id"])
                    for fr in track["frames"]:
                        fid = fr["frame"]
                        if fid not in tracks_by_frame:
                            tracks_by_frame[fid] = []
                        
                        tracks_by_frame[fid].append({
                            "id": gid,
                            "bbox": fr["bbox"],
                            "type": "person" # Default
                        })
            
            self.videos[video_name] = {
                "path": str(vpath),
                "cap": cv2.VideoCapture(str(vpath)),
                "offset": offset,
                "status": "waiting", # waiting, playing, finished
                "tracks": tracks_by_frame,
                "frame_count": 0
            }
            print(f"Loaded {video_name}: Offset={offset:.1f}s")

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
        
        while self.running:
            start_loop = time.time()
            
            frames_to_show = []
            
            active_videos = 0
            
            for vid_id, vdata in self.videos.items():
                cap = vdata["cap"]
                offset = vdata["offset"]
                
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
                            # Scale bbox if we resized frame
                            # Original size? We don't know original size here easily without reading cap prop.
                            # Assuming 640x360 is close or we need to scale.
                            # Let's assume we draw on original frame then resize? No, slow.
                            # Let's just draw on resized frame. We need scale factor.
                            # Quick hack: Read frame size once.
                            h_orig = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                            w_orig = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                            sx = 640 / w_orig
                            sy = 360 / h_orig
                            
                            sx1, sy1 = int(x1*sx), int(y1*sy)
                            sx2, sy2 = int(x2*sx), int(y2*sy)
                            
                            # Color based on ID
                            color = ((det["id"] * 50) % 255, (det["id"] * 100) % 255, (det["id"] * 200) % 255)
                            
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

        cv2.destroyAllWindows()

if __name__ == "__main__":
    dashboard = DashboardV()
    dashboard.load_resources()
    dashboard.run()
