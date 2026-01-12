import time
import csv
import json
import logging
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("AlertManager")

class AlertManager:
    def __init__(self, output_file="outputs/events/events.jsonl", min_duration=2.0):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.min_duration = min_duration

        # Tracking active intrusions:
        # {track_id: {zone_id: {start_time: float, confirmed: bool}}}
        self.active_intrusions = defaultdict(dict)

        self._format = self.output_file.suffix.lower()
        if self._format not in {".csv", ".jsonl"}:
            # Default to JSONL if unknown
            self._format = ".jsonl"

        # Initialize CSV if needed
        if self._format == ".csv" and not self.output_file.exists():
            with open(self.output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp",
                    "event_type",
                    "video_id",
                    "track_id",
                    "class_name",
                    "zone_id",
                    "duration",
                    "frame_id",
                    "t",
                    "t_sync",
                ])

    def update(self, track_id, zone_ids, frame_time, video_id, frame_id, class_name=None, t_sync=None):
        """
        Update intrusion status for a track.
        zone_ids: list of zones the track is currently in.
        """
        current_time = frame_time
        current_time_sync = t_sync
        
        # Check for new or continuing intrusions
        for zone_id in zone_ids:
            if zone_id not in self.active_intrusions[track_id]:
                # New intrusion
                self.active_intrusions[track_id][zone_id] = {
                    "start_time": current_time,
                    "confirmed": False,
                }

                # Immediate confirmation mode
                if self.min_duration <= 0 and not self.active_intrusions[track_id][zone_id]["confirmed"]:
                    self.active_intrusions[track_id][zone_id]["confirmed"] = True
                    self.log_event(
                        event_type="intrusion_confirmed",
                        video_id=video_id,
                        track_id=track_id,
                        class_name=class_name,
                        zone_id=zone_id,
                        duration=0.0,
                        frame_id=frame_id,
                        t=current_time,
                        t_sync=current_time_sync,
                    )
            else:
                # Continuing intrusion - check duration
                start_time = self.active_intrusions[track_id][zone_id]["start_time"]
                duration = current_time - start_time

                if duration >= self.min_duration and not self.active_intrusions[track_id][zone_id]["confirmed"]:
                    self.active_intrusions[track_id][zone_id]["confirmed"] = True
                    self.log_event(
                        event_type="intrusion_confirmed",
                        video_id=video_id,
                        track_id=track_id,
                        class_name=class_name,
                        zone_id=zone_id,
                        duration=duration,
                        frame_id=frame_id,
                        t=current_time,
                        t_sync=current_time_sync,
                    )

        # Check for ended intrusions
        for zone_id in list(self.active_intrusions[track_id].keys()):
            if zone_id not in zone_ids:
                # Intrusion ended
                start_time = self.active_intrusions[track_id][zone_id]["start_time"]
                duration = current_time - start_time

                if self.active_intrusions[track_id][zone_id].get("confirmed"):
                    self.log_event(
                        event_type="intrusion_ended",
                        video_id=video_id,
                        track_id=track_id,
                        class_name=class_name,
                        zone_id=zone_id,
                        duration=duration,
                        frame_id=frame_id,
                        t=current_time,
                        t_sync=current_time_sync,
                    )

                del self.active_intrusions[track_id][zone_id]

    def log_event(self, event_type, video_id, track_id, class_name, zone_id, duration, frame_id, t=None, t_sync=None):
        """Log confirmed intrusion event to CSV or JSONL."""
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")

            if self._format == ".csv":
                with open(self.output_file, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        ts,
                        event_type,
                        video_id,
                        track_id,
                        class_name,
                        zone_id,
                        f"{duration:.2f}",
                        frame_id,
                        f"{t:.3f}" if t is not None else "",
                        f"{t_sync:.3f}" if t_sync is not None else "",
                    ])
            else:
                payload = {
                    "timestamp": ts,
                    "event_type": event_type,
                    "video_id": video_id,
                    "track_id": track_id,
                    "class_name": class_name,
                    "zone_id": zone_id,
                    "duration": float(duration),
                    "frame_id": int(frame_id),
                }
                if t is not None:
                    payload["t"] = float(t)
                if t_sync is not None:
                    payload["t_sync"] = float(t_sync)

                with open(self.output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Error logging event: {e}")

    def get_active_alerts(self, track_id, current_time):
        """Return list of active alerts (duration > threshold) for visualization"""
        alerts = []
        if track_id in self.active_intrusions:
            for zone_id, start_time in self.active_intrusions[track_id].items():
                duration = current_time - start_time["start_time"]
                if duration >= self.min_duration:
                    alerts.append((zone_id, duration))
        return alerts
