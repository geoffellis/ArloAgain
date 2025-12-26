import time
import cv2
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
from pathlib import Path
from dotenv import load_dotenv
from ultralytics import YOLO

# Load environment variables
load_dotenv()

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "C:/Users/geoff/Videos/Arlo"))

# Initialize YOLO model (will download yolov8n.pt on first run)
model = YOLO('yolov8n.pt')

class FileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.mp4'):
            filepath = event.src_path
            print(f"New file detected: {filepath}")
            self.process_file(filepath)

    def process_file(self, filepath):
        # Your processing logic here (e.g., read, analyze, move, or delete the file)
        try:
            
            print(f"Scanning {filepath} for people...")
            
            # Open video with OpenCV to manage resources manually
            cap = cv2.VideoCapture(filepath)
            if not cap.isOpened():
                print(f"Could not open video: {filepath}")
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
                        break
            finally:
                cap.release()
            
            if not person_detected:
                print(f"No person found in: {filepath}")
                
        except Exception as e:
            print(f"Error processing {filepath}: {e}")

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