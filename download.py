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
import os
import sys
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
            await asyncio.sleep(60)
            
            # Detailed Heartbeat Logging to monitor for "stale" states
            cameras = arlo.cameras
            camera_count = len(cameras) if cameras else 0
            base_stations = arlo.base_stations
            bs_count = len(base_stations) if base_stations else 0
            
            logger.info(f"Heartbeat: {camera_count} cameras, {bs_count} base stations detected.")
            
            if cameras:
                for cam in cameras:
                    # Try 'state' or 'is_unavailable' which are more common in 0.8.x
                    state = getattr(cam, 'state', 'unknown')
                    online = "offline" if getattr(cam, 'is_unavailable', False) else "online"
                    status = f"{state} ({online})"
                    logger.info(f"  - {cam.name}: status={status}")

            # If we lose all cameras, the session is likely dead or has been cleared by a failed refresh
            if camera_count == 0:
                logger.error("Health check failed: 0 cameras detected. Terminating process for systemd restart.")
                os._exit(1)

    except KeyboardInterrupt:
        logger.info("Shutting down listener...")
        raise
    except Exception as e:
        logger.error(f"Critical error in event listener: {e}. Terminating process.")
        os._exit(1)

async def main():
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
            tfa_delay=10,
            mode_api='v2',
            save_media_to=str(DOWNLOAD_DIR / "arlo_${Y}${m}${d}_${H}${M}${S}"),
            library_days=1,  # Load recordings from the last 7 days
            refresh_devices_every=30,
            stream_timeout=180,
            reconnect_every=90,
            request_timeout=120
        ))

        if not arlo.cameras or len(arlo.cameras) == 0:
            logger.error("Arlo initialized but found 0 cameras. This indicates a stale session. Terminating.")
            os._exit(1)

        logger.info(f"Arlo initialized. Found {len(arlo.cameras)} cameras: {[c.name for c in arlo.cameras]}")

        await listen_for_events(arlo)
    except KeyboardInterrupt:
        logger.info("Exiting application...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Critical connection failure: {e}. Terminating process.")
        os._exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass