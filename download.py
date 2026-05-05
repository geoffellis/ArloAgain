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
import asyncio
import time
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import pyaarlo
import pyaarlo.location
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

async def listen_for_events(arlo):
    """Listen for new media events and download videos."""
    logger.info("Starting Arlo event listener...")

    def on_new_capture(device, attr, value):
        logger.info(f"New capture detected on {device.name} (Attribute: {attr})")
        # Note: Download is handled automatically by save_media_to in PyArlo constructor

    # Register callbacks for all cameras
    for camera in arlo.cameras:
        logger.info(f"Registering callback for camera: {camera.name}")
        camera.add_attr_callback('lastCaptureTime', on_new_capture)

    try:
        while True:
            await asyncio.sleep(1)  # Keep the main thread alive

    except KeyboardInterrupt:
        logger.info("Shutting down listener...")
        raise
    except Exception as e:
        logger.error(f"Error in event listener: {e}")

async def main():
    while True:
        try:
            logger.info("Authenticating with Arlo...")
            loop = asyncio.get_event_loop()
            arlo = await loop.run_in_executor(None, lambda: pyaarlo.PyArlo(
                username=ARLO_USERNAME,
                password=ARLO_PASSWORD,
                tfa_source='imap',
                tfa_type='email',
                tfa_host=ARLO_2FA_HOST,
                tfa_username=ARLO_2FA_EMAIL,
                tfa_password=ARLO_2FA_PASSWORD,
                tfa_total_retries=20,
                tfa_delay=3,
                mode_api='v2',
                save_media_to=str(DOWNLOAD_DIR / "arlo_${Y}${m}${d}_${H}${M}${S}"),
                library_days=0,  # Disable media library loading to prevent errors
                refresh_devices_every=3,
                stream_timeout=180,
                reconnect_every=90,
                request_timeout=120
            ))

            await listen_for_events(arlo)
        except KeyboardInterrupt:
            logger.info("Exiting application...")
            break
        except Exception as e:
            logger.error(f"Connection lost or failed: {e}")
            logger.info("Restarting in 60 seconds...")
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass