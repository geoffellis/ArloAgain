import time
import json
import cv2
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
from pathlib import Path
from dotenv import load_dotenv
from ultralytics import YOLO
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load environment variables
load_dotenv()

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "C:/Users/geoff/Videos/Arlo"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

PROCESSED_LOG = DOWNLOAD_DIR / "processed_files.jsonl"
MAX_LOG_AGE_DAYS = 8

TEMP_EXTENSIONS = {'.tmp', '.part'}

# Slack Configuration
SLACK_API_TOKEN = os.getenv("SLACK_API_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")

# Initialize YOLO model (will download yolov8n.pt on first run)
model = YOLO('yolov8n.pt')

class FileHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.processed_files = {}
        self._load_processed_log()

    def _load_processed_log(self):
        cutoff = datetime.now() - timedelta(days=MAX_LOG_AGE_DAYS)
        if not PROCESSED_LOG.exists():
            return

        valid_records = []
        with PROCESSED_LOG.open('r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    processed_at = datetime.fromisoformat(entry['processed_at'])
                    filepath = entry['filepath']
                except Exception:
                    continue

                if processed_at >= cutoff:
                    valid_records.append(entry)
                    self.processed_files[filepath] = processed_at

        if not valid_records:
            PROCESSED_LOG.unlink(missing_ok=True)
            return

        with PROCESSED_LOG.open('w', encoding='utf-8') as file:
            for entry in valid_records:
                file.write(json.dumps(entry) + '\n')

    def _is_processed(self, filepath):
        filepath = str(Path(filepath).resolve())
        return filepath in self.processed_files

    def _record_processed_file(self, filepath):
        filepath = str(Path(filepath).resolve())
        entry = {
            'filepath': filepath,
            'processed_at': datetime.now().isoformat()
        }
        self.processed_files[filepath] = datetime.fromisoformat(entry['processed_at'])
        with PROCESSED_LOG.open('a', encoding='utf-8') as file:
            file.write(json.dumps(entry) + '\n')

    def _cleanup_processed_file(self, filepath):
        # No longer deleting files - they stay in download directory
        # A separate cron routine will purge old videos
        pass

    def on_created(self, event):
        if event.is_directory:
            return

        suffix = Path(event.src_path).suffix.lower()
        if suffix in TEMP_EXTENSIONS or suffix != '.mp4':
            return

        filepath = event.src_path
        if Path(filepath).parent == DOWNLOAD_DIR:
            print(f"New file detected: {filepath}")
            self.process_file(filepath)

    def on_moved(self, event):
        if event.is_directory:
            return

        suffix = Path(event.dest_path).suffix.lower()
        if suffix in TEMP_EXTENSIONS or suffix != '.mp4':
            return

        filepath = event.dest_path
        if Path(filepath).parent == DOWNLOAD_DIR:
            print(f"New file detected (renamed): {filepath}")
            self.process_file(filepath)

    def process_existing_files(self):
        """Process any .mp4 files already present in the watched folder."""
        for existing_file in DOWNLOAD_DIR.glob('*.mp4'):
            filepath = str(existing_file.resolve())
            if self._is_processed(filepath):
                print(f"Already processed on startup, skipping: {filepath}")
                continue
            print(f"Found existing file: {filepath}")
            self.process_file(filepath)

    def process_file(self, filepath):
        filepath_resolved = str(Path(filepath).resolve())
        if self._is_processed(filepath_resolved):
            print(f"Already processed, skipping: {filepath_resolved}")
            return

        try:
            print(f"Scanning {filepath} for people...")

            cap = cv2.VideoCapture(filepath)
            if not cap.isOpened():
                print(f"Could not open video: {filepath}")
                self._record_processed_file(filepath_resolved)
                return

            person_detected = False
            frame_skip = 5  # Process every 5th frame to speed up
            frame_count = 0

            try:
                while True:
                    success, frame = cap.read()
                    if not success:
                        break

                    frame_count += 1
                    if frame_count % frame_skip != 0:
                        continue

                    results = model(frame, classes=[0], conf=0.5, verbose=False)

                    if len(results[0].boxes) > 0:
                        person_detected = True
                        print(f"⚠️ PERSON DETECTED in: {filepath}")

                        image_path = str(Path(filepath).with_suffix('.jpg'))
                        cv2.imwrite(image_path, frame)

                        if SLACK_API_TOKEN:
                            try:
                                client = WebClient(token=SLACK_API_TOKEN)
                                client.files_upload_v2(
                                    channel=SLACK_CHANNEL_ID,
                                    file=image_path,
                                    title="Person Detected",
                                    initial_comment=f"⚠️ Person detected in video: {os.path.basename(filepath)}\n📅 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                                )
                                print(f"Slack notification sent to {SLACK_CHANNEL_ID}")
                            except SlackApiError as e:
                                error_msg = e.response['error']
                                print(f"Error sending Slack notification: {error_msg}")
                                if error_msg == 'invalid_arguments' and str(SLACK_CHANNEL_ID).startswith('#'):
                                    print(f"Tip: SLACK_CHANNEL_ID must be a Channel ID (e.g., C12345), not a name ({SLACK_CHANNEL_ID}).")
                        break
            finally:
                cap.release()

            if not person_detected:
                print(f"No person found in: {filepath}")

            self._record_processed_file(filepath_resolved)

        except Exception as e:
            print(f"Error processing {filepath}: {e}")

if __name__ == '__main__':
    event_handler = FileHandler()
    event_handler.process_existing_files()

    observer = Observer()
    observer.schedule(event_handler, path=DOWNLOAD_DIR, recursive=False)  # Watch only top-level dir
    observer.start()
    print(f"Watching directory: {DOWNLOAD_DIR}")
    try:
        while True:
            time.sleep(1)  # Keep the observer running
    except KeyboardInterrupt:
        observer.stop()
    observer.join()