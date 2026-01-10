import time
import csv
import logging
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger("AlertManager")

class AlertManager:
    def __init__(self, output_file="outputs/events.csv", min_duration=2.0):
        self.output_file = Path(output_file)
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        self.min_duration = min_duration
        
        # Tracking active intrusions: {track_id: {zone_id: start_time}}
        self.active_intrusions = defaultdict(dict)
        
        # Initialize CSV if needed
        if not self.output_file.exists():
            with open(self.output_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "video_id", "track_id", "zone_id", "duration", "frame_id"])

    def update(self, track_id, zone_ids, frame_time, video_id, frame_id):
        """
        Update intrusion status for a track.
        zone_ids: list of zones the track is currently in.
        """
        current_time = frame_time
        
        # Check for new or continuing intrusions
        for zone_id in zone_ids:
            if zone_id not in self.active_intrusions[track_id]:
                # New intrusion
                self.active_intrusions[track_id][zone_id] = current_time
                # logger.info(f"Intrusion started: Track {track_id} in {zone_id}")
            else:
                # Continuing intrusion - check duration
                start_time = self.active_intrusions[track_id][zone_id]
                duration = current_time - start_time
                
                if duration >= self.min_duration:
                    # Log event (could limit to once per intrusion or periodically)
                    # For now, we'll log it if it's exactly crossing the threshold or periodically?
                    # Let's just return it as an active alert to be visualized/logged
                    pass

        # Check for ended intrusions
        ended_zones = []
        for zone_id in list(self.active_intrusions[track_id].keys()):
            if zone_id not in zone_ids:
                # Intrusion ended
                start_time = self.active_intrusions[track_id][zone_id]
                duration = current_time - start_time
                
                if duration >= self.min_duration:
                    self.log_event(video_id, track_id, zone_id, duration, frame_id)
                    logger.info(f"Intrusion confirmed: Track {track_id} in {zone_id} for {duration:.1f}s")
                
                del self.active_intrusions[track_id][zone_id]

    def log_event(self, video_id, track_id, zone_id, duration, frame_id):
        """Log confirmed intrusion event to CSV"""
        try:
            with open(self.output_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    video_id,
                    track_id,
                    zone_id,
                    f"{duration:.2f}",
                    frame_id
                ])
        except Exception as e:
            logger.error(f"Error logging event: {e}")

    def get_active_alerts(self, track_id, current_time):
        """Return list of active alerts (duration > threshold) for visualization"""
        alerts = []
        if track_id in self.active_intrusions:
            for zone_id, start_time in self.active_intrusions[track_id].items():
                duration = current_time - start_time
                if duration >= self.min_duration:
                    alerts.append((zone_id, duration))
        return alerts
