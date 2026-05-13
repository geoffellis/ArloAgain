import time
import json
import cv2
import av
import queue
import threading
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
DEEP_SCAN_SKIP = int(os.getenv("DEEP_SCAN_SKIP", "10"))

# Initialize YOLO model (will download yolov8n.pt on first run)
model = YOLO('yolov8n.pt')

class FileHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.processed_files = {}
        self.queue = queue.Queue()
        self._load_processed_log()
        
        # Start the background worker thread
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

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

    def _record_processed_file(self, filepath, detection_data=None):
        filepath = str(Path(filepath).resolve())
        entry = {
            'filepath': filepath,
            'processed_at': datetime.now().isoformat()
        }
        if detection_data:
            entry.update(detection_data)

        self.processed_files[filepath] = datetime.fromisoformat(entry['processed_at'])
        with PROCESSED_LOG.open('a', encoding='utf-8') as file:
            file.write(json.dumps(entry) + '\n')

    def _cleanup_processed_file(self, filepath):
        # No longer deleting files - they stay in download directory
        # A separate cron routine will purge old videos
        pass

    def _worker(self):
        """Background worker to process files from the queue one by one."""
        while True:
            filepath = self.queue.get()
            try:
                self.process_file(filepath)
            except Exception as e:
                print(f"Worker thread error: {e}")
            finally:
                self.queue.task_done()

    def on_created(self, event):
        if event.is_directory:
            return

        suffix = Path(event.src_path).suffix.lower()
        if suffix in TEMP_EXTENSIONS or suffix != '.mp4':
            return

        filepath = event.src_path
        if Path(filepath).parent == DOWNLOAD_DIR:
            print(f"New file detected: {filepath}")
            self.queue.put(filepath)

    def on_moved(self, event):
        if event.is_directory:
            return

        suffix = Path(event.dest_path).suffix.lower()
        if suffix in TEMP_EXTENSIONS or suffix != '.mp4':
            return

        filepath = event.dest_path
        if Path(filepath).parent == DOWNLOAD_DIR:
            print(f"New file detected (renamed): {filepath}")
            self.queue.put(filepath)

    def process_existing_files(self):
        """Process any .mp4 files already present in the watched folder, oldest first."""
        files = list(DOWNLOAD_DIR.glob('*.mp4'))
        # Sort by modification time (oldest first)
        files.sort(key=lambda x: x.stat().st_mtime)

        for existing_file in files:
            filepath = str(existing_file.resolve())
            if self._is_processed(filepath):
                print(f"Already processed on startup, skipping: {filepath}")
                continue
            print(f"Found existing file (queued oldest to newest): {filepath}")
            self.queue.put(filepath)

    def _detect_person(self, frame):
        """Runs YOLO detection on a frame and returns (found, boxes)."""
        results = model(frame, classes=[0], conf=0.5, verbose=False)
        if len(results[0].boxes) > 0:
            return True, results[0].boxes.xyxy.tolist()
        return False, []

    def _handle_person_detected(self, filepath, frame):
        """Handles image saving and Slack notification."""
        print(f"⚠️ PERSON DETECTED in: {filepath}")
        image_path = Path(filepath).with_suffix('.jpg')
        cv2.imwrite(str(image_path), frame)

        if SLACK_API_TOKEN:
            try:
                client = WebClient(token=SLACK_API_TOKEN)
                client.files_upload_v2(
                    channel=SLACK_CHANNEL_ID,
                    file=str(image_path),
                    title="Person Detected",
                    initial_comment=f"⚠️ Person detected in video: {os.path.basename(filepath)}\n📅 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                print(f"Slack notification sent to {SLACK_CHANNEL_ID}")
            except SlackApiError as e:
                error_msg = e.response['error']
                print(f"Error sending Slack notification: {error_msg}")
        return image_path.name

    def process_file(self, filepath):
        filepath_resolved = str(Path(filepath).resolve())
        if self._is_processed(filepath_resolved):
            print(f"Already processed, skipping: {filepath_resolved}")
            return

        try:
            person_detected = False
            detection_data = {
                "person_found": False,
                "image_name": None,
                "bounding_boxes": []
            }

            # Pass 1: Key Frame Pass (I-frames only)
            print(f"Pass 1: Scanning I-frames in {filepath}...")
            with av.open(filepath) as container:
                stream = container.streams.video[0]
                # demux() allows us to check packet headers without decoding the whole frame
                for packet in container.demux(stream):
                    if packet.is_keyframe:
                        for frame in packet.decode():
                            # Convert PyAV frame to BGR numpy array for YOLO/OpenCV
                            img = frame.to_ndarray(format='bgr24')
                            found, boxes = self._detect_person(img)
                            if found:
                                person_detected = True
                                image_name = self._handle_person_detected(filepath, img)
                                detection_data.update({
                                    "person_found": True,
                                    "image_name": image_name,
                                    "bounding_boxes": boxes
                                })
                                break
                    if person_detected:
                        break

            # Pass 2: Deep Scan (Scan every single frame)
            if not person_detected:
                print(f"No person found in I-frames. Pass 2: Scanning every {DEEP_SCAN_SKIP} frames in {filepath}...")
                cap = cv2.VideoCapture(filepath)
                if not cap.isOpened():
                    print(f"Could not open video: {filepath}")
                    self._record_processed_file(filepath_resolved, detection_data)
                    return

                try:
                    frame_count = 0
                    while True:
                        success, frame = cap.read()
                        if not success:
                            break

                        if frame_count % DEEP_SCAN_SKIP == 0:
                            found, boxes = self._detect_person(frame)
                            if found:
                                person_detected = True
                                print(f"🎯 DEEP SCAN SUCCESS: Person detected in {filepath} (missed by I-frames)")
                                image_name = self._handle_person_detected(filepath, frame)
                                detection_data.update({
                                    "person_found": True,
                                    "image_name": image_name,
                                    "bounding_boxes": boxes
                                })
                                break
                        frame_count += 1
                finally:
                    cap.release()

            if not person_detected:
                print(f"No person found in: {filepath}")

            self._record_processed_file(filepath_resolved, detection_data)

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