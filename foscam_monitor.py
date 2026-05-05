import os
"""
Foscam G2 Camera Monitor and Video Downloader
This module provides functionality to connect to a Foscam G2 camera,
monitor for motion events, and automatically download video recordings or snapshots to a
local directory.
Module Overview:
    - Connects to Foscam G2 camera using IP, username, and password
    - Monitors for motion detection events via polling
    - Automatically downloads snapshots when motion is detected
    - Logs all activities to both file and console
Configuration:
    FOSCAM_IP (str): IP address of the Foscam camera
    FOSCAM_USERNAME (str): Camera username
    FOSCAM_PASSWORD (str): Camera password
    DOWNLOAD_DIR (Path): Local directory for storing downloaded files
    LOG_FILE (Path): Path to log file for recording activities
Functions:
    download_snapshot(ip, user, pwd, filename): Downloads a snapshot using HTTP API
    check_motion(ip, user, pwd): Checks if motion is detected (polling method)
    listen_for_motion(ip, user, pwd): Listens for motion events and manages downloads
    main(): Main entry point for connection and monitoring
Note:
    This implementation uses direct HTTP API calls to the Foscam camera, as pyfoscontrol is outdated.
    For better motion detection, consider setting up HTTP notifications in the camera's Alarm Center.
"""
import time
import logging
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
FOSCAM_IP = os.getenv("FOSCAM_IP", "192.168.1.100")  # Default IP, change as needed
FOSCAM_USERNAME = os.getenv("FOSCAM_USERNAME", "admin")
FOSCAM_PASSWORD = os.getenv("FOSCAM_PASSWORD")
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "C:/Users/geoff/Videos/Foscam"))
LOG_FILE = Path(os.getenv("LOG_FILE", "C:/Users/geoff/OneDrive/Documents/ArloAgain/foscam.log"))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

def download_snapshot(ip, user, pwd, filename):
    """Download a snapshot from the camera using HTTP API."""
    url = f"http://{ip}/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2&usr={user}&pwd={pwd}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with open(filename, 'wb') as f:
            f.write(response.content)
        logging.info(f"Snapshot downloaded: {filename}")
    except Exception as e:
        logging.error(f"Failed to download snapshot: {e}")

def check_motion(ip, user, pwd):
    """Check if motion is detected (basic polling, may not be accurate)."""
    # Foscam has cmd=getMotionDetectConfig, but for detection, this is simplistic
    # In practice, motion detection is handled by the camera's firmware
    # This is a placeholder; for real monitoring, use camera's HTTP notification feature
    # For now, assume motion if we can get a snapshot (always true)
    # To improve, perhaps compare snapshots or use RTSP stream
    return True  # Placeholder

def listen_for_motion(ip, user, pwd):
    """Listen for motion events and download snapshots."""
    last_motion_time = 0
    while True:
        try:
            if check_motion(ip, user, pwd):
                current_time = time.time()
                if current_time - last_motion_time > 60:  # Download every minute as example
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = DOWNLOAD_DIR / f"foscam_snapshot_{timestamp}.jpg"
                    download_snapshot(ip, user, pwd, filename)
                    last_motion_time = current_time
            time.sleep(10)  # Poll every 10 seconds
        except Exception as e:
            logging.error(f"Error in motion detection: {e}")
            time.sleep(30)

def main():
    """Main entry point."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if not FOSCAM_PASSWORD:
        logging.error("FOSCAM_PASSWORD not set in environment variables")
        return

    logging.info("Starting Foscam monitor")
    listen_for_motion(FOSCAM_IP, FOSCAM_USERNAME, FOSCAM_PASSWORD)

if __name__ == "__main__":
    main()