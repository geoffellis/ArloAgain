import os
"""
Arlo Video Download and Motion Event Listener
This module provides functionality to authenticate with Arlo security systems,
monitor for motion events, and automatically download video recordings to a
local directory.
Module Overview:
    - Authenticates with Arlo Base Station using credentials
    - Continuously monitors media library for new recordings
    - Automatically downloads videos when motion is detected
    - Logs all activities to both file and console
Configuration:
    ARLO_USERNAME (str): Arlo account email address
    ARLO_PASSWORD (str): Arlo account password
    DOWNLOAD_DIR (Path): Local directory for storing downloaded videos
    LOG_FILE (Path): Path to log file for recording activities
Functions:
    download_video(arlo, recording, filename): Downloads a single video recording
    listen_for_events(arlo): Listens for motion events and manages downloads
    main(): Main entry point for authentication and event monitoring
Note:
    This implementation uses the 'pyaarlo' library which supports 2FA via IMAP.
    Ensure your Gmail account has IMAP enabled and you are using an App Password.
"""
import time
import threading
import logging
from datetime import datetime
from pathlib import Path
import pyaarlo
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
ARLO_USERNAME = os.getenv("ARLO_USERNAME")
ARLO_PASSWORD = os.getenv("ARLO_PASSWORD")
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "C:/Users/geoff/Videos/Arlo"))
LOG_FILE = Path(os.getenv("LOG_FILE", "C:/Users/geoff/OneDrive/Documents/ArloAgain/download.log"))
ARLO_2FA_EMAIL = os.getenv("ARLO_2FA_EMAIL")
ARLO_2FA_PASSWORD = os.getenv("ARLO_2FA_PASSWORD")
ARLO_2FA_HOST = os.getenv("ARLO_2FA_HOST", "imap.gmail.com")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create download directory if it doesn't exist
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def download_video(arlo, recording, filename):
    """Download a single video recording."""
    try:
        logger.info(f"Downloading: {filename}")
        recording.download_video(str(DOWNLOAD_DIR / filename))
        logger.info(f"Successfully downloaded: {filename}")
        return True
    except Exception as e:
        logger.error(f"Error downloading {filename}: {e}")
        return False

def check_for_new_media(arlo):
    """Check media library and download new videos."""
    try:
        # pyaarlo property access triggers a refresh of the library
        for recording in arlo.media_library:
            timestamp = datetime.fromtimestamp(int(recording.created_at) / 1000.0)
            filename = f"arlo_{timestamp.strftime('%Y%m%d_%H%M%S')}.mp4"
            filepath = DOWNLOAD_DIR / filename
            
            # Download if not already present
            if not filepath.exists():
                download_video(arlo, recording, filename)
    except Exception as e:
        logger.error(f"Error checking media library: {e}")

def listen_for_events(arlo):
    """Listen for new media events and download videos."""
    logger.info("Starting Arlo event listener...")

    def on_new_capture(device, attr, value):
        logger.info(f"New capture detected on {device.name} (Attribute: {attr})")
        # Run check in separate thread to avoid blocking the event listener
        threading.Thread(target=check_for_new_media, args=(arlo,)).start()

    # Register callbacks for all cameras
    for camera in arlo.cameras:
        logger.info(f"Registering callback for camera: {camera.name}")
        camera.add_attr_callback('lastCaptureTime', on_new_capture)

    # Initial check to catch anything missed while offline
    check_for_new_media(arlo)
    
    try:
        while True:
            time.sleep(1)  # Keep the main thread alive
            
    except KeyboardInterrupt:
        logger.info("Shutting down listener...")
        raise
    except Exception as e:
        logger.error(f"Error in event listener: {e}")

def main():
    while True:
        try:
            logger.info("Authenticating with Arlo...")
            arlo = pyaarlo.PyArlo(
                username=ARLO_USERNAME,
                password=ARLO_PASSWORD,
                tfa_source='imap',
                tfa_type='email',
                tfa_host=ARLO_2FA_HOST,
                tfa_username=ARLO_2FA_EMAIL,
                tfa_password=ARLO_2FA_PASSWORD
            )
            listen_for_events(arlo)
        except KeyboardInterrupt:
            logger.info("Exiting application...")
            break
        except Exception as e:
            logger.error(f"Connection lost or failed: {e}")
            logger.info("Restarting in 60 seconds...")
            time.sleep(60)

if __name__ == "__main__":
    main()