import cv2
import json
import time
import numpy as np
from pathlib import Path
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


def _find_offset_for_video(video_name: str, offsets: dict) -> float | None:
    """Best-effort mapping between video filename and offsets file keys."""
    if not offsets:
        return None
    for key, val in offsets.items():
        try:
            if video_name in str(key):
                return float(val)
        except Exception:
            continue
    return None

class DashboardV:
    def __init__(
        self,
        data_dir="data",
        *,
        offset_source: str = "timestamp",
        offset_file: str | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.videos_dir = self.data_dir / "videos"
        self.traj_dir = self.data_dir / "trajectories"
        self.offsets_durree_file = self.data_dir / "camera_offsets_durree.json"
        self.offsets_timestamp_file = self.data_dir / "camera_offsets_timestamp.json"
        self.offset_source = str(offset_source)
        self.offset_file = offset_file
        
        self.analyzer = GlobalAnalyzer(data_dir)
        
        self.videos = {} # video_id -> {cap, offset, status, data, current_frame_idx}
        self.global_time = 0.0
        # We start the dashboard at a synchronized time where every video has started.
        # Concretely, we pick t_sync_start = max(raw_offsets) and seek each capture accordingly.
        self.t_sync_start = 0.0
        self.target_fps = 30.0
        self.running = False

    def load_resources(self):
        """Loads videos, offsets, and trajectory data."""
        print("[Dashboard] Loading resources...")
        
        # 0. Run Global Analysis
        self.analyzer.load_data()
        
        # 1. Load Offsets (timestamp/duration + optional custom)
        offsets_timestamp = {}
        offsets_durree = {}
        offsets_custom = {}

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

        if self.offset_file:
            try:
                custom_path = Path(self.offset_file)
                if custom_path.exists():
                    offsets_custom = json.loads(custom_path.read_text(encoding="utf-8"))
            except Exception:
                offsets_custom = {}
        
        # 2. Find Videos and Load Data
        video_files = list(self.videos_dir.glob("*.mp4"))
        
        for vpath in video_files:
            # Guess video_id (filename without extension)
            # Note: The offset file uses keys like "CAMERA_X_full". 
            # The video file might be "CAMERA_X.mp4".
            # We need to match them.
            video_name = vpath.stem

            # Raw sync offset selection for the dashboard.
            # - trajectory: use trajectories' sync_offset first, fallback timestamp then duration
            # - timestamp: use timestamp file
            # - duration: use duration file
            # - custom: use --offset-file json
            # - none: 0 for all
            offset = 0.0
            if self.offset_source == "timestamp":
                found = _find_offset_for_video(video_name, offsets_timestamp)
                offset = float(found) if found is not None else 0.0
            elif self.offset_source == "duration":
                found = _find_offset_for_video(video_name, offsets_durree)
                offset = float(found) if found is not None else 0.0
            elif self.offset_source == "custom":
                found = _find_offset_for_video(video_name, offsets_custom)
                offset = float(found) if found is not None else 0.0
            elif self.offset_source == "none":
                offset = 0.0
            else:
                # trajectory (default): temporary value; may be overridden by traj_data sync_offset.
                found = _find_offset_for_video(video_name, offsets_timestamp)
                if found is None:
                    found = _find_offset_for_video(video_name, offsets_durree)
                offset = float(found) if found is not None else 0.0
            
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
                if self.offset_source in ("trajectory", "auto"):
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
                    track_id = track.get("track_id")
                    class_name = track.get("class_name") or "person"
                    for fr in track["frames"]:
                        fid = fr["frame"]
                        if fid not in tracks_by_frame:
                            tracks_by_frame[fid] = []
                        
                        tracks_by_frame[fid].append({
                            "global_id": gid_val,
                            "track_id": track_id,
                            "bbox": fr["bbox"],
                            "class_name": class_name,
                        })

            # Cache capture properties + compute scale factors once per video
            cap = cv2.VideoCapture(str(vpath))
            w_orig = float(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            h_orig = float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or self.target_fps)
            total_frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration_s = (total_frames / fps) if fps > 0 and total_frames > 0 else None

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
                # raw_offset is the original sync offset (seconds) used when writing t_sync.
                "raw_offset": float(offset),
                "rotation_applied": rotation_applied,
                "status": "playing", # playing, finished
                "tracks": tracks_by_frame,
                "frame_count": 0,
                "fps": fps,
                "total_frames": int(total_frames) if total_frames else None,
                "duration_s": duration_s,
                "sx": sx,
                "sy": sy,
            }
            print(f"Loaded {video_name}: Offset={offset:.1f}s | Rotation={rotation_applied}°")

        # Pick a synchronized start time so every camera has frames to show.
        # Ideally, we pick t_sync_start inside the intersection of [offset, offset+duration] across videos.
        if self.videos:
            starts = []
            ends = []
            for v in self.videos.values():
                raw_offset = float(v.get("raw_offset", 0.0))
                starts.append(raw_offset)
                dur = v.get("duration_s")
                if dur is not None:
                    try:
                        ends.append(raw_offset + float(dur))
                    except Exception:
                        pass

            max_start = max(starts) if starts else 0.0
            min_end = min(ends) if ends else None

            if min_end is not None and max_start <= min_end:
                self.t_sync_start = float(max_start)
                print(f"[Dashboard] t_sync_start (overlap) = {self.t_sync_start:.1f}s")
            else:
                # No global overlap across all videos; fallback to max offset (everyone has started)
                # Some videos might already be finished; we'll clamp the seek.
                self.t_sync_start = float(max_start)
                print(
                    f"[Dashboard] WARNING: pas de chevauchement commun entre toutes les vidéos. "
                    f"Fallback t_sync_start={self.t_sync_start:.1f}s (seek + clamp)."
                )

            for vid_id, v in self.videos.items():
                fps = float(v.get("fps", self.target_fps) or self.target_fps)
                raw_offset = float(v.get("raw_offset", 0.0))
                total_frames = v.get("total_frames")

                local_start_s = self.t_sync_start - raw_offset
                if local_start_s < 0:
                    local_start_s = 0.0

                # OpenCV frame index is 0-based; our pipeline frame_id is 1-based.
                # We set cap to (frame_id-1), and keep frame_count aligned to frame_id-1.
                start_frame_1based = int(round(local_start_s * fps)) + 1
                cap_pos_0based = max(0, start_frame_1based - 1)

                # Clamp seek to video length if known.
                if total_frames is not None:
                    try:
                        total_frames_i = int(total_frames)
                        if total_frames_i > 1 and cap_pos_0based >= total_frames_i:
                            cap_pos_0based = total_frames_i - 1
                    except Exception:
                        pass

                # Seek the capture to local_start_s.
                # On some Windows/OpenCV builds, seeking by milliseconds is more reliable than by frames.
                cap = v.get("cap")
                try:
                    if cap is not None:
                        cap.set(cv2.CAP_PROP_POS_MSEC, float(local_start_s) * 1000.0)
                except Exception:
                    pass
                try:
                    if cap is not None:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, cap_pos_0based)
                except Exception:
                    pass
                v["frame_count"] = cap_pos_0based
                v["local_start_s"] = float(local_start_s)

                print(f"[Dashboard] {vid_id}: t_sync_start={self.t_sync_start:.1f}s -> local_start={local_start_s:.1f}s (frame~{start_frame_1based})")

    def run(self):
        """Main playback loop."""
        self.running = True

        if not self.videos:
            print("[Dashboard] Aucun fichier .mp4 trouvé dans data/videos/. Rien à afficher.")
            return
        
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
                    raw_offset = float(vdata.get("raw_offset", 0.0))
                    rotation_applied = int(vdata.get("rotation_applied", 0))
                    sx = float(vdata.get("sx", 1.0))
                    sy = float(vdata.get("sy", 1.0))
                    fps = float(vdata.get("fps", self.target_fps) or self.target_fps)

                    # In this dashboard mode, all videos start immediately (we pre-seeked them).
                    if vdata.get("status") != "finished":
                        vdata["status"] = "playing"
                    
                    # Get Frame
                    frame = None
                    
                    if vdata["status"] == "playing":
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            vdata["frame_count"] += 1
                            active_videos += 1

                            # Apply same rotation as used during processing so bboxes align.
                            try:
                                frame = _apply_rotation(frame, rotation_applied)
                            except Exception:
                                # Fallback to original frame if rotation fails
                                pass
                            
                            # Resize for grid (optional, but good for performance)
                            frame = cv2.resize(frame, (640, 360))
                            
                            # Draw Detections
                            # We read sequentially; frame_count matches the stored 1-based frame index.
                            current_fid = vdata["frame_count"]
                            
                            detections = vdata["tracks"].get(current_fid, [])
                            for det in detections:
                                x1, y1, x2, y2 = det["bbox"]
                                
                                sx1, sy1_ = int(x1 * sx), int(y1 * sy)
                                sx2, sy2_ = int(x2 * sx), int(y2 * sy)

                                global_id = det.get("global_id")
                                track_id = det.get("track_id")
                                class_name = det.get("class_name") or "person"

                                # Color based on ID (global_id preferred, fallback to local track_id)
                                color_key = global_id if global_id is not None else track_id
                                color = _stable_color(color_key)

                                # Zone intrusion (live check) for better visibility
                                in_zones: list[str] = []
                                try:
                                    cx = int((x1 + x2) / 2)
                                    cy = int((y1 + y2) / 2)
                                    in_zones = self.analyzer.zone_manager.check_point_all_zones(cx, cy, camera_id=vid_id)
                                except Exception:
                                    in_zones = []

                                box_color = (0, 0, 255) if in_zones else color
                                thickness = 3 if in_zones else 2

                                cv2.rectangle(frame, (sx1, sy1_), (sx2, sy2_), box_color, thickness)

                                if global_id is not None:
                                    label = f"GID {global_id}"
                                else:
                                    label = f"TID {track_id}"
                                if class_name:
                                    label = f"{label} | {class_name}"

                                cv2.putText(
                                    frame,
                                    label,
                                    (sx1, max(15, sy1_ - 5)),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.5,
                                    box_color,
                                    1,
                                )

                                # If in zone, show zone name(s)
                                if in_zones:
                                    # Show first zone name (or ids) on bbox
                                    zid = str(in_zones[0])
                                    z = getattr(self.analyzer.zone_manager, "zones", {}).get(zid, {})
                                    zname = z.get("name") if isinstance(z, dict) else None
                                    zlabel = zname or zid
                                    cv2.putText(
                                        frame,
                                        f"ALERTE: {zlabel}",
                                        (sx1, min(350, sy2_ + 18)),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.6,
                                        (0, 0, 255),
                                        2,
                                    )

                                # Story overlay (only for global_id)
                                if global_id is not None:
                                    story = self.analyzer.get_story(global_id)
                                else:
                                    story = None
                                if story:
                                    # Show path summary (last 3 cameras)
                                    path_str = " -> ".join(
                                        [p["camera"].replace("CAMERA_", "")[:3] for p in story["path"][-3:]]
                                    )
                                    cv2.putText(
                                        frame,
                                        path_str,
                                        (sx1, min(350, sy2_ + 35)),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.4,
                                        (255, 255, 255),
                                        1,
                                    )
                        else:
                            vdata["status"] = "finished"
                            frame = np.zeros((360, 640, 3), dtype=np.uint8)
                            cv2.putText(
                                frame,
                                "Finished",
                                (200, 180),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                1,
                                (0, 0, 255),
                                2,
                            )
                    else:
                        frame = np.zeros((360, 640, 3), dtype=np.uint8)
                        cv2.putText(
                            frame,
                            "Finished",
                            (200, 180),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,
                            (0, 0, 255),
                            2,
                        )

                    # Ensure consistent tile format for stacking.
                    if frame is None:
                        frame = np.zeros((360, 640, 3), dtype=np.uint8)
                    elif getattr(frame, "ndim", 0) == 2:
                        try:
                            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                        except Exception:
                            frame = np.zeros((360, 640, 3), dtype=np.uint8)
                    if frame.shape[0] != 360 or frame.shape[1] != 640:
                        try:
                            frame = cv2.resize(frame, (640, 360))
                        except Exception:
                            frame = np.zeros((360, 640, 3), dtype=np.uint8)

                    # Add label
                    status = vdata.get("status", "?")
                    cv2.putText(
                        frame,
                        f"{vid_id} [{status}]",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                    )

                    # Add local time hint
                    if vdata.get("status") == "playing":
                        local_t = (float(vdata.get("frame_count", 0)) / fps) if fps > 0 else 0.0
                        t_sync = float(self.t_sync_start) + float(self.global_time)
                        cv2.putText(
                            frame,
                            f"t={local_t:.1f}s  raw_offset={raw_offset:.1f}s  t_sync={t_sync:.1f}s",
                            (10, 55),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.55,
                            (200, 200, 200),
                            1,
                        )

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
                cv2.putText(
                    final_grid,
                    f"t_sync = {self.t_sync_start + self.global_time:.2f}s  (delta={self.global_time:.2f}s)",
                    (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.2,
                    (0, 255, 255),
                    3,
                )

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
