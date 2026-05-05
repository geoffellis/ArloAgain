import time
import cv2
import shutil
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

PROCESSED_DIR = DOWNLOAD_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Slack Configuration
SLACK_API_TOKEN = os.getenv("SLACK_API_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")

# Initialize YOLO model (will download yolov8n.pt on first run)
model = YOLO('yolov8n.pt')

class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.mp4'):
            filepath = event.src_path
            if Path(filepath).parent == DOWNLOAD_DIR:
                print(f"New file detected: {filepath}")
                self.process_file(filepath)

    def on_moved(self, event):
        if not event.is_directory and event.dest_path.lower().endswith('.mp4'):
            filepath = event.dest_path
            if Path(filepath).parent == DOWNLOAD_DIR:
                print(f"New file detected (renamed): {filepath}")
                self.process_file(filepath)

    def process_file(self, filepath):
        # Your processing logic here (e.g., read, analyze, move, or delete the file)
        try:
            
            print(f"Scanning {filepath} for people...")
            
            # Open video with OpenCV to manage resources manually
            cap = cv2.VideoCapture(filepath)
            if not cap.isOpened():
                print(f"Could not open video: {filepath}")
                self._move_to_processed(filepath)
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

                    # Run inference on the frame
                    results = model(frame, classes=[0], conf=0.5, verbose=False)
                    
                    if len(results[0].boxes) > 0:
                        person_detected = True
                        print(f"⚠️ PERSON DETECTED in: {filepath}")

                        # Save the detected frame as a JPG
                        image_path = str(Path(filepath).with_suffix('.jpg'))
                        cv2.imwrite(image_path, frame)

                        # Send notification to Slack
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
            
            self._move_to_processed(filepath)
                
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

    def _move_to_processed(self, filepath):
        """Moves the video and any associated images to the processed subfolder."""
        try:
            video_path = Path(filepath)
            if not video_path.exists():
                return

            dest_video = PROCESSED_DIR / video_path.name
            
            # Handle filename collisions in the processed folder
            if dest_video.exists():
                timestamp = time.strftime("%Y%m%d-%H%M%S")
                dest_video = PROCESSED_DIR / f"{video_path.stem}_{timestamp}{video_path.suffix}"

            # Check for and move associated jpg if it exists
            image_path = video_path.with_suffix('.jpg')
            if image_path.exists():
                dest_jpg = PROCESSED_DIR / f"{dest_video.stem}.jpg"
                shutil.move(str(image_path), str(dest_jpg))

            shutil.move(str(video_path), str(dest_video))
            print(f"Moved {video_path.name} to {PROCESSED_DIR}")
        except Exception as e:
            print(f"Error moving {filepath} to processed: {e}")

if __name__ == '__main__':
    event_handler = FileHandler()
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